"""Structural data audit (S1): aggregate measurements over loaded recordings.

`measure()` is deterministic. The same recordings produce an identical result dict, because no
wall-clock values are included and floats are rounded. It uses only production loader outputs
(ADR-005), and its medication and meal checks are *structural* (presence, vocabulary, amount+unit
patterns, timing alignment). Clinical normalisation is the S3 medication parser's job.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from hyposense.data.loader import cgm_series
from hyposense.data.quality import QualityThresholds, cgm_quality_flags
from hyposense.data.records import Recording
from hyposense.data.summary import FORBIDDEN_FEATURE_COLUMNS, SummaryTable

# Only these fields may appear per recording (aggregate-only safeguard, P-C5).
PER_RECORDING_FIELDS = (
    "recording_key",
    "patient_id",
    "file_format",
    "header_variant_index",
    "rows",
    "cgm_readings",
    "first_local_date",
    "duration_days",
    "issues_error",
    "issues_warning",
    "issues_info",
)
MED_TEXT_COLUMNS = ("insulin_sc", "oral_agents", "insulin_iv")
MED_NUMERIC_COLUMNS = ("csii_bolus", "csii_basal")
# ASCII and full-width (Chinese) comma / semicolon separators
_SPLIT = re.compile("[,;\n\uff0c\uff1b]+")
_AMOUNT = re.compile(r"\d+(?:\.\d+)?\s*(?:iu|u|units?|mg|g|µg|ug|ml)\b", re.IGNORECASE)
_AMOUNT_BY_COLUMN = {
    "insulin_sc": re.compile(r"\d+(?:\.\d+)?\s*(?:iu|u|units?)\b", re.IGNORECASE),
    "oral_agents": re.compile(r"\d+(?:\.\d+)?\s*(?:mg|g)\b", re.IGNORECASE),
    "insulin_iv": re.compile(r"\d+(?:\.\d+)?\s*(?:iu|u|units?|ml)\b", re.IGNORECASE),
}


def _r(x: float, nd: int = 6) -> float:
    return float(round(float(x), nd))


def _rate(num: int, den: int) -> float | None:
    return _r(num / den) if den else None


def _components(text: str) -> list[str]:
    return [p.strip() for p in _SPLIT.split(text) if p.strip()]


def _drug_name(component: str) -> str:
    name = _AMOUNT.sub(" ", component.lower())
    name = re.sub("[():\uff08\uff09\uff1a]", " ", name)  # incl. full-width ( ) :
    return re.sub(r"\s+", " ", name).strip(" .-")


def _interval_bin(minutes: float) -> str:
    """Interval bins in minutes: <14, 14-16, (16,20], (20,30], (30,60], >60."""
    if minutes < 14:
        return "a:<14"
    if minutes <= 16:
        return "b:14-16"
    if minutes <= 20:
        return "c:(16,20]"
    if minutes <= 30:
        return "d:(20,30]"
    if minutes <= 60:
        return "e:(30,60]"
    return "f:>60"


def measure(
    recordings: Sequence[Recording],
    summary: SummaryTable | None,
    thresholds: QualityThresholds,
    max_interval_min: float,
) -> dict[str, Any]:
    recs = sorted(recordings, key=lambda r: r.identity.recording_key)
    issue_counts: Counter[tuple[str, str]] = Counter()
    variants: dict[str, int] = {}
    variant_files: Counter[str] = Counter()
    per_rec: list[dict[str, Any]] = []
    intervals_all: list[np.ndarray] = []
    bp_intervals: list[np.ndarray] = []  # blueprint definition: all non-null CGM rows
    excluded_total: Counter[str] = Counter()
    cgm_vals: list[np.ndarray] = []
    durations: list[float] = []
    bp_days: list[float] = []
    flags_total: Counter[str] = Counter()
    med: dict[str, Counter[str]] = {c: Counter() for c in (*MED_TEXT_COLUMNS, *MED_NUMERIC_COLUMNS)}
    vocab: dict[str, Counter[str]] = {c: Counter() for c in MED_TEXT_COLUMNS}
    meal: Counter[str] = Counter()
    align: Counter[str] = Counter()
    day_cov: list[float] = []
    by_patient: dict[str, list[tuple[int, int, int]]] = {}
    unit_check: dict[str, list[float]] = {}
    no_cgm_rows: dict[str, int] = {}
    entry_hours: dict[str, Counter[int]] = {
        c: Counter() for c in ("insulin_sc", "oral_agents", "diet_en")
    }
    rows_total = rows_ts_valid = cgm_nonempty = cgm_parsed = 0
    cbg_n = 0
    cbg_recs = 0
    calendar_days = 0

    for rec in recs:
        f = rec.frame
        ident = rec.identity
        for i in rec.issues:
            issue_counts[(i.severity, i.code.value)] += 1
        vidx = variants.setdefault(rec.header_variant, len(variants))
        variant_files[rec.header_variant] += 1
        rows_total += len(f)
        rows_ts_valid += int(f["ts_valid"].sum())
        has_cgm = f["cgm"].notna().to_numpy()
        raw_cgm = f["raw_cgm"].notna().to_numpy()
        cgm_nonempty += int((has_cgm | raw_cgm).sum())
        cgm_parsed += int((has_cgm & f["ts_valid"].to_numpy(bool)).sum())

        s = cgm_series(rec)
        excluded_total.update(s.excluded)
        cgm_vals.append(s.value)
        if rec.unitless_columns:
            unit_check.setdefault("unitless_header_files", []).extend(s.value.tolist())
        if len(s.ts) > 1:
            intervals_all.append(np.diff(s.ts) / 60.0)
        dur = float((s.ts[-1] - s.ts[0]) / 86400.0) if len(s.ts) else 0.0
        durations.append(dur)
        qf = cgm_quality_flags(s, thresholds)
        flags_total["gap_before"] += int(qf.gap_before.sum())
        flags_total["floor"] += int(qf.floor.sum())
        flags_total["rapid_change"] += int(qf.rapid_change.sum())
        flags_total["warmup"] += int(qf.warmup.sum())

        # blueprint-comparable definitions (original audit: every non-null CGM row, sorted)
        bp = f.loc[has_cgm & f["ts_valid"].to_numpy(bool), "ts"].to_numpy(np.int64)
        if len(bp) > 1:
            bp_intervals.append(np.diff(bp) / 60.0)
            # original audit: per-recording days rounded to 2 dp, then summed (audit.py l.109/164)
            bp_days.append(round(float((bp[-1] - bp[0]) / 86400.0), 2))
        rows_without_cgm = int((~has_cgm & ~raw_cgm).sum())
        if rows_without_cgm:
            no_cgm_rows[ident.recording_key] = rows_without_cgm

        local_dates = pd.to_datetime(f.loc[f["ts_valid"], "ts_local"]).dt.date
        cgm_dates = set(
            pd.to_datetime(f.loc[has_cgm & f["ts_valid"].to_numpy(bool), "ts_local"]).dt.date
        )
        calendar_days += len(cgm_dates)
        cgm_ts = set(s.ts.tolist())

        # medication (structural)
        med_days: set[object] = set()
        for c in (*MED_TEXT_COLUMNS, *MED_NUMERIC_COLUMNS):
            present = f[c].notna() | (f[f"raw_{c}"].notna() if f"raw_{c}" in f else False)
            n = int(present.sum())
            med[c]["entries"] += n
            med[c]["recordings_with"] += int(n > 0)
            if n:
                med_days |= set(local_dates[present & f["ts_valid"]])
            for idx in np.flatnonzero(present.to_numpy()):
                row = f.iloc[idx]
                align["entries"] += 1
                align["on_cgm_row"] += int(pd.notna(row["cgm"]))
                align["at_cgm_timestamp"] += int(bool(row["ts_valid"]) and int(row["ts"]) in cgm_ts)
            if c in MED_TEXT_COLUMNS:
                pat = _AMOUNT_BY_COLUMN[c]
                for text in f.loc[f[c].notna(), c]:
                    med[c]["entries_with_amount_unit"] += int(bool(pat.search(str(text))))
                    for p in _components(str(text)):
                        name = _drug_name(p)
                        if name:  # a bare amount component ("14 IU") names no drug
                            vocab[c][name] += 1
            else:
                med[c]["text_cells"] += int(f[f"raw_{c}"].notna().sum())
        if med_days and cgm_dates:
            day_cov.append(len(med_days & cgm_dates) / len(cgm_dates))

        # meals
        diet = f["diet_en"].dropna().astype(str)
        meal["diet_en_entries"] += len(diet)
        meal["diet_en_not_available"] += int(diet.str.lower().str.contains("not available").sum())
        meal["diet_cn_entries"] += int(f["diet_cn"].notna().sum())
        meal["both_languages"] += int((f["diet_en"].notna() & f["diet_cn"].notna()).sum())
        meal["recordings_with_diet"] += int(len(diet) > 0)
        meal["diet_on_cgm_row"] += int((f["diet_en"].notna() & f["cgm"].notna()).sum())

        # local-hour histograms: aggregate evidence for the +08:00 local-clock ASSUMPTION
        for c in ("insulin_sc", "oral_agents", "diet_en"):
            sel = f[c].notna() & f["ts_valid"]
            entry_hours[c].update(pd.to_datetime(f.loc[sel, "ts_local"]).dt.hour.tolist())

        cbg_rows = int(f["cbg"].notna().sum())
        cbg_n += cbg_rows
        cbg_recs += int(cbg_rows > 0)

        if len(s.ts):
            by_patient.setdefault(ident.patient_id, []).append(
                (int(s.ts[0]), int(s.ts[-1]), ident.period)
            )
        sev = Counter(i.severity for i in rec.issues)
        first_date = (
            str(pd.Timestamp(f.loc[f["ts_valid"], "ts_local"].min()).date())
            if f["ts_valid"].any()
            else None
        )
        per_rec.append(
            {
                "recording_key": ident.recording_key,
                "patient_id": ident.patient_id,
                "file_format": ident.file_format,
                "header_variant_index": vidx,
                "rows": len(f),
                "cgm_readings": len(s.ts),
                "first_local_date": first_date,
                "duration_days": _r(dur, 3),
                "issues_error": sev["error"],
                "issues_warning": sev["warning"],
                "issues_info": sev["info"],
            }
        )

    iv = np.concatenate(intervals_all) if intervals_all else np.zeros(0)
    bpi = np.concatenate(bp_intervals) if bp_intervals else np.zeros(0)
    vals = np.concatenate(cgm_vals) if cgm_vals else np.zeros(0)
    patients = sorted({r.identity.patient_id for r in recs})
    recs_per_patient = Counter(Counter(r.identity.patient_id for r in recs).values())
    overlaps = sum(
        1
        for spans in by_patient.values()
        for i, a in enumerate(spans)
        for b in spans[i + 1 :]
        if a[0] <= b[1] and b[0] <= a[1]
    )
    non_chrono = sum(
        1
        for spans in by_patient.values()
        if [p for _, _, p in sorted(spans)] != sorted(p for _, _, p in spans)
    )
    hist = Counter(_interval_bin(m) for m in iv)
    bp_hist = Counter(
        "<=16" if m <= 16 else ("16-30" if m <= 30 else ("30-60" if m <= 60 else ">60"))
        for m in bpi
    )
    q = np.percentile(vals, [0, 1, 50, 99, 100]) if len(vals) else [np.nan] * 5
    unit_vals = np.asarray(unit_check.get("unitless_header_files", []))

    results: dict[str, Any] = {
        "dataset": {
            "recording_files": len(recs),
            "recordings": len({r.identity.recording_key for r in recs}),
            "patients": len(patients),
            "recordings_per_patient": {str(k): v for k, v in sorted(recs_per_patient.items())},
            "patients_with_multiple_recordings": sum(
                v for k, v in recs_per_patient.items() if k > 1
            ),
            "rows": rows_total,
            "rows_without_cgm": sum(no_cgm_rows.values()),
            "rows_without_cgm_by_recording": dict(sorted(no_cgm_rows.items())),
            "cgm_readings": len(vals),
            "monitored_days": _r(sum(durations), 3),
            "patient_days": _r(sum(durations), 3),
            "calendar_days_with_cgm": calendar_days,
            "recording_days_min_median_max": [
                _r(min(durations), 3),
                _r(float(np.median(durations)), 3),
                _r(max(durations), 3),
            ]
            if durations
            else None,
        },
        "identity": {
            "file_name_pattern_violations": 0,  # discovery is strict: any violation raises
            "sheet_name_mismatches": sorted(
                i.recording_key
                for r in recs
                for i in r.issues
                if i.code.value == "sheet_name_mismatch"
            ),
            "nominal_start_mismatches": sorted(
                i.recording_key
                for r in recs
                for i in r.issues
                if i.code.value == "nominal_start_mismatch"
            ),
            "overlapping_recording_pairs_within_patient": overlaps,
            "patients_with_non_chronological_period_index": non_chrono,
            "summary": _summary_identity(recs, summary),
        },
        "schema": {
            "header_variants": [
                {"index": variants[v], "n_files": variant_files[v], "headers": v}
                for v in sorted(variants, key=lambda k: variants[k])
            ],
            "n_header_variants": len(variants),
            "files_with_unitless_headers": sum(1 for r in recs if r.unitless_columns),
            "unitless_header_cgm_median": _r(float(np.median(unit_vals)), 1)
            if len(unit_vals)
            else None,
            "unitless_header_cgm_in_mgdl_range": bool(
                len(unit_vals) and 20 <= np.median(unit_vals) <= 600
            ),
        },
        "timestamps": {
            "rows_with_valid_timestamp": rows_ts_valid,
            "timestamp_parse_rate": _rate(rows_ts_valid, rows_total),
            "assumed_utc_offset": None,  # filled by caller from config
            "entry_local_hour_histogram": {
                c: {str(h): v[h] for h in range(24) if v[h]} for c, v in entry_hours.items()
            },
            "cgm_intervals": len(iv),
            "interval_histogram_min": {k: hist[k] for k in sorted(hist)},
            "interval_le_max_rate": _rate(int((iv <= max_interval_min).sum()), len(iv)),
            "interval_exactly_15_rate": _rate(int((np.abs(iv - 15) < 1).sum()), len(iv)),
            "gaps_gt_30_min": int((iv > 30).sum()),
            "gaps_gt_60_min": int((iv > 60).sum()),
            "max_gap_min": _r(float(iv.max()), 2) if len(iv) else None,
        },
        "cgm": {
            "cells_nonempty": cgm_nonempty,
            "parsed_with_valid_timestamp": cgm_parsed,
            "parse_rate": _rate(cgm_parsed, cgm_nonempty),
            "series_readings": len(vals),
            "excluded_from_series": dict(sorted(excluded_total.items())),
            "min_p1_median_p99_max": [_r(x, 1) for x in q],
            "out_of_plausible_range": issue_counts[("warning", "cgm_out_of_range")],
            "at_or_below_floor": flags_total["floor"],
            "fraction_multiple_of_1_8": _rate(
                int(np.sum(np.isclose(np.mod(vals + 1e-9, 1.8), 0, atol=1e-6))), len(vals)
            ),
            "quality_flags": dict(sorted(flags_total.items())),
        },
        "cbg": {"values": cbg_n, "recordings_with": cbg_recs},
        "medication": {
            "columns": {c: dict(sorted(v.items())) for c, v in med.items()},
            "entries_with_amount_unit_rate": {
                c: _rate(med[c]["entries_with_amount_unit"], med[c]["entries"])
                for c in MED_TEXT_COLUMNS
            },
            "vocabulary": {
                c: dict(sorted(v.items(), key=lambda kv: (-kv[1], kv[0]))) for c, v in vocab.items()
            },
            "vocabulary_size": {c: len(v) for c, v in vocab.items()},
            "administration_alignment": {
                "entries": align["entries"],
                "on_cgm_row_rate": _rate(align["on_cgm_row"], align["entries"]),
                "at_cgm_timestamp_rate": _rate(align["at_cgm_timestamp"], align["entries"]),
            },
            "median_day_coverage_recordings_with_entries": (
                _r(float(np.median(day_cov)), 4) if day_cov else None
            ),
        },
        "meals": dict(sorted(meal.items())),
        "summary": _summary_schema(summary),
        "issues": {f"{s}:{c}": n for (s, c), n in sorted(issue_counts.items())},
        "blueprint_definitions": {
            "recordings": len(recs),
            "patients": len(patients),
            "n_header_variants": len(variants),
            "cgm_rows": cgm_parsed,
            "monitor_days": _r(sum(bp_days), 1),
            "days_per_recording": (
                [_r(min(bp_days), 2), _r(float(np.median(bp_days)), 2), _r(max(bp_days), 2)]
                if bp_days
                else None
            ),
            "interval_hist": dict(sorted(bp_hist.items())),
            "readings_le40": int(np.sum(vals <= 40)),
            "min_cgm": _r(float(vals.min()), 1) if len(vals) else None,
            "ins_sc_entries": med["insulin_sc"]["entries"],
            "oral_entries": med["oral_agents"]["entries"],
            "recs_ins_sc": med["insulin_sc"]["recordings_with"],
            "recs_oral": med["oral_agents"]["recordings_with"],
            "recs_iv": med["insulin_iv"]["recordings_with"],
            "recs_csii": sum(
                1
                for r in recs
                if (
                    r.frame["csii_bolus"].notna()
                    | r.frame["raw_csii_bolus"].notna()
                    | r.frame["csii_basal"].notna()
                    | r.frame["raw_csii_basal"].notna()
                ).any()
            ),
            "diet_entries": meal["diet_en_entries"],
            "diet_not_available": meal["diet_en_not_available"],
            "cbg_values": cbg_n,
            "recs_with_cbg": cbg_recs,
        },
        "per_recording": per_rec,
    }
    return results


def _summary_identity(recs: Sequence[Recording], summary: SummaryTable | None) -> dict[str, Any]:
    if summary is None:
        return {"present": False}
    keys = {r.identity.recording_key for r in recs}
    skeys = set(map(str, summary.frame.index))
    return {
        "present": True,
        "rows": len(skeys),
        "recordings_without_summary_row": sorted(keys - skeys),
        "summary_rows_without_recording": sorted(skeys - keys),
    }


def _summary_schema(summary: SummaryTable | None) -> dict[str, Any]:
    if summary is None:
        return {"present": False}
    df = summary.frame
    missing = {
        c: int(df[c].isna().sum() + (df[c].astype(str).str.strip() == "").sum())
        for c in df.columns
        if c not in FORBIDDEN_FEATURE_COLUMNS
    }
    dtype_counts = Counter(str(v).strip() for v in df["diabetes_type"].dropna())
    return {
        "present": True,
        "rows": len(df),
        "columns": len(df.columns) + 1,  # + recording_key index
        "missing_by_column": dict(sorted(missing.items())),
        "diabetes_type_values": dict(sorted(dtype_counts.items())),
        "forbidden_columns_present": sorted(FORBIDDEN_FEATURE_COLUMNS & set(df.columns)),
        "forbidden_column_values_reported": False,
    }
