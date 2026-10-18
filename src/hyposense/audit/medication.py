"""Medication audit (S3): vocabulary inventory, parser coverage, production treated status, pump and
i.v. investigations, G3 inputs, and representation QA. OFFLINE.

AGGREGATE-ONLY for the sealed partition (P-C5):
- The inventory reports raw medication strings, which are outcome-blind vocabulary, with
  counts per partition.
- Treated status is a medication-derived, outcome-blind population attribute.
- The i.v.-glucose "near a CGM low" count is aggregate.
- Representation QA (feature distributions) runs on TUNING (T) recordings ONLY.
"""

from __future__ import annotations

import itertools
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from hyposense.data.loader import cgm_series
from hyposense.data.records import Recording
from hyposense.data.summary import SummaryTable
from hyposense.labels.build import label_recording
from hyposense.labels.config import LabelConfig
from hyposense.medication.dictionary import DrugDictionary
from hyposense.medication.events import EventKind, Flag, ParseStatus
from hyposense.medication.exposure import ExposureEngine, KernelSet
from hyposense.medication.recording import (
    RecordingMedication,
    TreatmentStatus,
    parse_recording,
    prescribed_classes,
    treatment_status,
)
from hyposense.medication.timing import raw_timing

TARGET = ("insulin", "sulfonylurea", "glinide")
DAY_S = 86400


def _r(x: float, nd: int = 4) -> float:
    return float(round(float(x), nd))


def _q(x: Sequence[float] | np.ndarray, qs: Sequence[float]) -> list[float] | None:
    return [_r(v, 3) for v in np.percentile(np.asarray(x, float), qs)] if len(x) else None


def parse_all(
    recordings: Sequence[Recording], d: DrugDictionary, rules: dict[str, Any]
) -> dict[str, RecordingMedication]:
    return {
        r.identity.recording_key: parse_recording(r, d, rules)
        for r in sorted(recordings, key=lambda r: r.identity.recording_key)
    }


def production_treated(
    recordings: Sequence[Recording], meds: dict[str, RecordingMedication]
) -> dict[str, TreatmentStatus]:
    by_patient: dict[str, list[RecordingMedication]] = defaultdict(list)
    for r in recordings:
        by_patient[r.identity.patient_id].append(meds[r.identity.recording_key])
    return {p: treatment_status(ms) for p, ms in sorted(by_patient.items())}


def inventory(
    recordings: Sequence[Recording], meds: dict[str, RecordingMedication], partition: dict[str, str]
) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for r in recordings:
        pid = r.identity.patient_id
        cgm_ts = set(cgm_series(r).ts.tolist())
        for en in meds[r.identity.recording_key].entries:
            key = (en.source_column, en.raw_text)
            row = rows.setdefault(
                key,
                {
                    "column": en.source_column,
                    "raw_text": en.raw_text,
                    "n": 0,
                    "patients": set(),
                    "recordings": set(),
                    "n_T": 0,
                    "n_E": 0,
                    "on_cgm_grid": 0,
                    "entry_status": en.status.value,
                    "components": [
                        {
                            "canonical": e.canonical,
                            "class": e.drug_class,
                            "kind": e.kind.value,
                            "route": e.route,
                            "formulation": e.formulation,
                            "formulation_basis": e.formulation_basis,
                            "dose": e.dose,
                            "unit": e.dose_unit,
                            "status": e.parse_status.value,
                            "flags": [f.value for f in e.flags],
                        }
                        for e in en.events
                    ],
                },
            )
            row["n"] += 1
            row["patients"].add(pid)
            row["recordings"].add(r.identity.recording_key)
            row[f"n_{partition.get(pid, '?')}"] = row.get(f"n_{partition.get(pid, '?')}", 0) + 1
            row["on_cgm_grid"] += int(en.events[0].ts in cgm_ts)
    out = []
    for row in rows.values():
        row["patients"] = len(row["patients"])
        row["recordings"] = len(row["recordings"])
        row["mapping_known"] = row["entry_status"] not in ("UNPARSEABLE",)
        row["ambiguous"] = row["entry_status"] == "AMBIGUOUS"
        out.append(row)
    return sorted(out, key=lambda x: (x["column"], -x["n"], x["raw_text"]))


def measure_medication(
    recordings: Sequence[Recording],
    summary: SummaryTable,
    meds: dict[str, RecordingMedication],
    partition: dict[str, str],
    d: DrugDictionary,
    ks: KernelSet,
    legacy_treated: dict[str, bool],
) -> dict[str, Any]:
    recs = sorted(recordings, key=lambda r: r.identity.recording_key)
    entries: Counter[tuple[str, str]] = Counter()
    kinds: Counter[tuple[str, str]] = Counter()
    flags: Counter[str] = Counter()
    canon: Counter[str | None] = Counter()
    classes: Counter[str | None] = Counter()
    routes: Counter[str | None] = Counter()
    target_admin: Counter[str] = Counter()
    sc_entries = sc_ok = oral_entries = oral_ok = 0
    su_form: Counter[str] = Counter()
    grid: Counter[str] = Counter()
    for r in recs:
        m = meds[r.identity.recording_key]
        cgm_ts = set(cgm_series(r).ts.tolist())
        for en in m.entries:
            entries[(en.source_column, en.status.value)] += 1
            comp_ok = all(
                e.parse_status not in (ParseStatus.UNPARSEABLE, ParseStatus.AMBIGUOUS)
                and (e.kind is not EventKind.ADMINISTRATION or e.dose is not None)
                for e in en.events
            )
            if en.source_column == "insulin_sc":
                sc_entries += 1
                sc_ok += comp_ok
            if en.source_column == "oral_agents":
                oral_entries += 1
                oral_ok += comp_ok
        for e in m.events:
            kinds[(e.kind.value, e.parse_status.value)] += 1
            flags.update(f.value for f in e.flags)
            if e.kind is EventKind.ADMINISTRATION and e.parse_status is not ParseStatus.UNPARSEABLE:
                canon[e.canonical] += 1
                classes[e.drug_class] += 1
                routes[e.route] += 1
            if (
                e.target
                and e.kind in (EventKind.ADMINISTRATION, EventKind.PUMP_BASAL_RATE)
                and e.drug_class in TARGET
            ):
                target_admin["events"] += 1
                target_admin["dose_known"] += e.dose is not None
                recognised = e.parse_status in (ParseStatus.PARSED, ParseStatus.PARSED_WITH_WARNING)
                target_admin["recognised"] += recognised
                target_admin["recognised_with_dose"] += recognised and e.dose is not None
                grid["target_events"] += 1
                grid["on_cgm_timestamp"] += e.ts in cgm_ts
            if e.drug_class == "sulfonylurea" and e.kind is EventKind.ADMINISTRATION:
                su_form[str(e.formulation_basis)] += 1
    unrecognised = sum(n for (c, s), n in entries.items() if s in ("UNPARSEABLE", "AMBIGUOUS"))

    # ---------------- patients / treated ----------------
    status = production_treated(recs, meds)
    patients = sorted(status)
    by_part: dict[str, Any] = {}
    for part in ("T", "E", "ALL"):
        mem = [p for p in patients if part == "ALL" or partition.get(p) == part]
        by_part[part] = {
            "patients": len(mem),
            "treated": sum(status[p].treated for p in mem),
            "insulin": sum(status[p].insulin for p in mem),
            "sulfonylurea": sum(status[p].sulfonylurea for p in mem),
            "glinide": sum(status[p].glinide for p in mem),
            "insulin_and_secretagogue": sum(
                status[p].insulin and (status[p].sulfonylurea or status[p].glinide) for p in mem
            ),
        }
    diff = [
        {
            "patient_id": p,
            "partition": partition.get(p),
            "legacy": legacy_treated.get(p),
            "production": status[p].treated,
        }
        for p in patients
        if bool(legacy_treated.get(p)) != status[p].treated
    ]

    # ---------------- prescribed vs logged (recording level) ----------------
    conflicts: Counter[str] = Counter()
    for r in recs:
        pres = prescribed_classes(
            summary.frame.loc[r.identity.recording_key, "prescribed_hypoglycemic_agents"], d
        )
        logged = {
            e.drug_class
            for e in meds[r.identity.recording_key].events
            if e.is_target_administration
        }
        for cls in TARGET:
            conflicts[f"{cls}_prescribed_not_logged"] += cls in pres and cls not in logged
            conflicts[f"{cls}_logged_not_prescribed"] += cls in logged and cls not in pres

    # ---------------- day coverage ----------------
    cov, cov_any = [], []
    for r in recs:
        m = meds[r.identity.recording_key]
        tgt = [e for e in m.events if e.is_target_administration]
        if not tgt:
            continue
        f = r.frame
        local = pd.to_datetime(f.loc[f["cgm"].notna() & f["ts_valid"], "ts_local"]).dt.date
        days = set(local)
        loc_of = dict(
            zip(
                f.loc[f["ts_valid"], "ts"].astype("int64").tolist(),
                pd.to_datetime(f.loc[f["ts_valid"], "ts_local"]).dt.date,
                strict=True,
            )
        )
        tdays = {loc_of[e.ts] for e in tgt if e.ts in loc_of}
        adays = {
            loc_of[e.ts] for e in m.events if e.kind is EventKind.ADMINISTRATION and e.ts in loc_of
        }
        cov.append(len(tdays & days) / len(days))
        cov_any.append(len(adays & days) / len(days))

    # ---------------- CSII ----------------
    csii: Counter[str] = Counter()
    seg_intervals: list[float] = []
    for r in recs:
        m = meds[r.identity.recording_key]
        basal = [
            e for e in m.events if e.kind in (EventKind.PUMP_BASAL_RATE, EventKind.PUMP_SUSPEND)
        ]
        if not basal and not any(e.route == "csii" for e in m.events):
            continue
        csii["recordings"] += 1
        csii["basal_entries"] += sum(e.kind is EventKind.PUMP_BASAL_RATE for e in basal)
        csii["suspend_entries"] += sum(e.kind is EventKind.PUMP_SUSPEND for e in basal)
        csii["zero_rate_entries"] += sum(
            e.kind is EventKind.PUMP_BASAL_RATE and e.dose == 0 for e in basal
        )
        csii["bolus_entries"] += sum(
            e.route == "csii" and e.kind is EventKind.ADMINISTRATION for e in m.events
        )
        csii["zero_boluses"] += sum(
            e.route == "csii" and Flag.ZERO_DOSE in e.flags for e in m.events
        )
        ts = [e.ts for e in basal]
        seg_intervals += [(b - a) / 60 for a, b in itertools.pairwise(ts)]
        last_cgm = int(cgm_series(r).ts[-1])
        if ts and ts[-1] + ks.max_continuation_s < last_cgm:
            csii["recordings_pump_entries_end_before_record_end"] += 1

    # ---------------- i.v. ----------------
    iv: Counter[str] = Counter()
    ivg: list[dict[str, Any]] = []
    for r in recs:
        m = meds[r.identity.recording_key]
        s = cgm_series(r)
        for e in m.events:
            if e.source_column != "insulin_iv":
                continue
            iv[f"{e.kind.value}:{e.drug_class}"] += 1
            if Flag.GLUCOSE_INFUSION in e.flags:
                near = (s.ts >= e.ts - 7200) & (s.ts <= e.ts + 7200)
                ivg.append(
                    {
                        "partition": partition.get(r.identity.patient_id),
                        "patient": r.identity.patient_id,
                        "volume_known": e.dose is not None,
                        "concentration_known": e.concentration_pct is not None,
                        "near_cgm_low": bool(np.any(s.value[near] < 70)),
                        "with_insulin_in_same_bag": any(
                            x.ts == e.ts and x.drug_class == "insulin" and x.route == "iv"
                            for x in m.events
                        ),
                    }
                )
    iv_glucose = {
        "events": len(ivg),
        "patients": len({g["patient"] for g in ivg}),
        "in_T": sum(g["partition"] == "T" for g in ivg),
        "in_E": sum(g["partition"] == "E" for g in ivg),
        "volume_and_concentration_known": sum(
            g["volume_known"] and g["concentration_known"] for g in ivg
        ),
        "rate_or_duration_known": 0,  # not recorded anywhere in the dataset
        "co_administered_with_iv_insulin": sum(g["with_insulin_in_same_bag"] for g in ivg),
        "with_cgm_below_70_within_2h": sum(g["near_cgm_low"] for g in ivg),
    }

    # ---------------- G3 inputs ----------------
    var_e = 0
    for p in patients:
        if partition.get(p) != "E" or not status[p].treated:
            continue
        tts = {
            e.ts
            for r in recs
            if r.identity.patient_id == p
            for e in meds[r.identity.recording_key].events
            if e.is_target_administration
        }
        var_e += len(tts) >= 2
    parse_den = target_admin["events"] + unrecognised
    return {
        "entries": {
            "total": sum(entries.values()),
            "by_column_status": {f"{c}:{s}": n for (c, s), n in sorted(entries.items())},
            "unrecognised_or_ambiguous": unrecognised,
        },
        "events": {
            "by_kind_status": {f"{k}:{s}": n for (k, s), n in sorted(kinds.items())},
            "flags": dict(sorted(flags.items())),
        },
        "administrations": {
            "canonical": dict(sorted(canon.items())),
            "class": dict(sorted(classes.items())),
            "route": dict(sorted(routes.items())),
        },
        "rates": {
            "insulin_sc_entries_parsed_to_drug_and_dose": [sc_ok, sc_entries],
            "oral_entries_parsed_to_drug_and_dose": [oral_ok, oral_entries],
            "target_administration_parse_rate": _r(target_admin["recognised_with_dose"] / parse_den)
            if parse_den
            else None,
            "target_dose_known_rate": _r(target_admin["dose_known"] / target_admin["events"])
            if target_admin["events"]
            else None,
            "sulfonylurea_formulation_basis": dict(sorted(su_form.items())),
            "target_events_on_cgm_timestamp_rate": _r(
                grid["on_cgm_timestamp"] / grid["target_events"]
            )
            if grid["target_events"]
            else None,
        },
        "treated": {
            "by_partition": by_part,
            "differs_from_legacy": diff,
            "definition": ">= 1 parsed administration of insulin (any route; CSII basal "
            "rate > 0 counts), a sulfonylurea or a glinide (Table 5.1)",
        },
        "prescribed_vs_logged_recordings": dict(sorted(conflicts.items())),
        "day_coverage_treated_recordings": {
            "recordings": len(cov),
            "target_admin_q1_median": _q(cov, [25, 50]),
            "target_admin_min": _r(min(cov)) if cov else None,
            "below_0_8": sum(c < 0.8 for c in cov),
            "any_administration_median_blueprint_style": _q(cov_any, [50]),
        },
        "csii": {
            **dict(sorted(csii.items())),
            "basal_entry_interval_min_q0_q50_q100": _q(seg_intervals, [0, 50, 100]),
        },
        "iv_column": dict(sorted(iv.items())),
        "iv_glucose": iv_glucose,
        "g3_inputs": {
            "parse_rate": _r(target_admin["recognised_with_dose"] / parse_den)
            if parse_den
            else None,
            "day_coverage_median": _r(float(np.median(cov))) if cov else None,
            "timing_on_grid_rate": _r(grid["on_cgm_timestamp"] / grid["target_events"])
            if grid["target_events"]
            else None,
            "timing_resolution_min": 15,
            "treated_E_patients_with_exposure_variation": var_e,
        },
    }


def representation_qa(
    t_recordings: Sequence[Recording],
    summary: SummaryTable,
    d: DrugDictionary,
    rules: dict[str, Any],
    ks: KernelSet,
    lc: LabelConfig,
) -> dict[str, Any]:
    """Distributions of planned M3 / M3r variables at label-eligible times — TUNING DATA ONLY."""
    feats: dict[str, list[np.ndarray]] = defaultdict(list)
    per_patient_sd: dict[str, list[float]] = defaultdict(list)
    steps: list[float] = []
    n_t = 0
    import time

    t0 = time.perf_counter()
    for r in sorted(t_recordings, key=lambda x: x.identity.recording_key):
        m = parse_recording(r, d, rules)
        if not any(e.is_target_administration for e in m.events):
            continue
        lab = label_recording(r, lc).prediction
        ts = lab.ts[lab.eligible]
        if not len(ts):
            continue
        pres = prescribed_classes(
            summary.frame.loc[r.identity.recording_key, "prescribed_hypoglycemic_agents"], d
        )
        out = ExposureEngine(m.events, ks, pres).compute(ts)
        out.update(raw_timing(m.events, ts))
        n_t += len(ts)
        for k, v in out.items():
            if k.startswith("quality_"):
                continue
            feats[k].append(v)
        a = out["act_insulin_total"]
        if np.isfinite(a).sum() > 1:
            per_patient_sd["act_insulin_total"].append(float(np.nanstd(a)))
            steps += np.abs(np.diff(a[np.isfinite(a)])).tolist()
        su = out["act_su"]
        if np.isfinite(su).sum() > 1 and np.nanmax(su) > 0:
            per_patient_sd["act_su"].append(float(np.nanstd(su)))
    elapsed = time.perf_counter() - t0
    stats = {}
    for k, parts in sorted(feats.items()):
        v = np.concatenate(parts)
        fin = v[np.isfinite(v)]
        stats[k] = {
            "n": len(v),
            "nan_share": _r(1 - len(fin) / len(v)) if len(v) else None,
            "zero_share": _r(float(np.mean(fin == 0))) if len(fin) else None,
            "p1_p50_p99_max": _q(fin, [1, 50, 99, 100]) if len(fin) else None,
        }
    allv = {k: np.concatenate(v) for k, v in feats.items()}

    def spearman(a: str, b: str) -> float | None:
        x, y = allv[a], allv[b]
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 10:
            return None
        rx = pd.Series(x[ok]).rank().to_numpy()
        ry = pd.Series(y[ok]).rank().to_numpy()
        return _r(float(np.corrcoef(rx, ry)[0, 1]), 3)

    return {
        "scope": "TUNING partition, treated recordings, label-eligible times",
        "readings": n_t,
        "seconds_per_1000_readings": _r(elapsed / max(n_t, 1) * 1000, 3),
        "features": stats,
        "within_recording_sd_q50": {k: _q(v, [50]) for k, v in per_patient_sd.items()},
        "recordings_with_varying_insulin_activity": sum(
            s > 0 for s in per_patient_sd["act_insulin_total"]
        ),
        "act_insulin_total_abs_step_q50_q99": _q(steps, [50, 99]),
        "spearman": {
            "act_insulin_total~iob_insulin": spearman("act_insulin_total", "iob_insulin"),
            "act_insulin_total~insulin_bolus_min_since_last": spearman(
                "act_insulin_total", "insulin_bolus_min_since_last"
            ),
            "act_insulin_total~insulin_bolus_dose_24h": spearman(
                "act_insulin_total", "insulin_bolus_dose_24h"
            ),
            "act_su~su_min_since_last": spearman("act_su", "su_min_since_last"),
            "insulin_p60~act_insulin_total": spearman("insulin_p60", "act_insulin_total"),
        },
    }
