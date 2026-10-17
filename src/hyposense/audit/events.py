"""Event audit (S2): aggregate event, prediction-time and label-validity measurements.

AGGREGATE-ONLY (approved P-C5). No per-patient or per-recording outcome values are emitted for
any patient. Partition-level totals (T vs E) are emitted because Gate G2 requires them.
Deterministic: the same recordings and config give an identical result dict.

The treated-patient breakdown uses the LEGACY (blueprint-audit) treated definition, marked
PROVISIONAL. The production definition arrives with the S3 medication parser, and G2 is then
re-evaluated.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from itertools import pairwise
from typing import Any

import numpy as np

from hyposense.audit.legacy import legacy_treatment, legacy_warnable
from hyposense.data.records import Recording
from hyposense.labels.annotations import annotate, floor_runs
from hyposense.labels.build import RecordingLabels, label_recording
from hyposense.labels.config import LabelConfig
from hyposense.labels.eligibility import Ineligibility, warnable_onsets
from hyposense.labels.episodes import Episode
from hyposense.labels.validity import (
    agreement_stats,
    cbg_series,
    episode_cbg_status,
    episode_cbg_status_onset_window,
    pair_cbg_cgm,
)

LEVELS = ("L1", "L2", "L1_single")


def _q(x: Sequence[float], qs: Sequence[float]) -> list[float] | None:
    return [round(float(v), 2) for v in np.percentile(np.asarray(x, float), qs)] if len(x) else None


def m_w(counts: Sequence[int]) -> float | None:
    """Effective cluster size sum(m^2) / sum(m) (Blueprint §8.6)."""
    s = sum(counts)
    return round(sum(c * c for c in counts) / s, 2) if s else None


def _per_patient_summary(
    per_patient: dict[str, int], all_patients: Sequence[str]
) -> dict[str, Any]:
    counts = [per_patient.get(p, 0) for p in all_patients]
    affected = [c for c in counts if c > 0]
    top = sorted(counts, reverse=True)
    total = sum(counts)
    return {
        "episodes": total,
        "patients_with": len(affected),
        "patients_without": len(counts) - len(affected),
        "per_affected_patient_q1_median_q3_max": (
            [*(_q(affected, [25, 50, 75]) or []), max(affected)] if affected else None
        ),
        "top5_counts": top[:5],
        "top5_share": round(sum(top[:5]) / total, 3) if total else None,
        "top1_share": round(top[0] / total, 3) if total else None,
        "m_w": m_w(counts),
    }


def measure_events(
    recordings: Sequence[Recording],
    cfg: LabelConfig,
    utc_offset_s: int,
    partition: dict[str, str],
    g3b: dict[str, Any],
) -> dict[str, Any]:
    recs = sorted(recordings, key=lambda r: r.identity.recording_key)
    labelled: list[tuple[Recording, RecordingLabels]] = [(r, label_recording(r, cfg)) for r in recs]
    patients = sorted({r.identity.patient_id for r in recs})

    per_patient: dict[str, Counter[str]] = defaultdict(Counter)
    end_reasons: dict[str, Counter[str]] = {lv: Counter() for lv in LEVELS}
    durations: dict[str, list[float]] = {lv: [] for lv in LEVELS}
    nadirs: dict[str, list[float]] = {lv: [] for lv in LEVELS}
    ann: Counter[str] = Counter()
    hours: Counter[int] = Counter()
    reasons: Counter[str] = Counter()
    coverage: list[float] = []
    inter_onset_min: list[float] = []
    end_to_next_min: list[float] = []
    edge: Counter[str] = Counter()
    pred = Counter[str]()
    warn = Counter[str]()
    treat_rec: dict[str, Any] = {}
    l1_rec_class: Counter[str] = Counter()
    pairs_cbg: list[np.ndarray] = []
    pairs_cgm: list[np.ndarray] = []
    during: Counter[str] = Counter()
    onset_window: Counter[str] = Counter()
    sensor_runs: Counter[str] = Counter()
    flagged_pp: Counter[str] = Counter()  # L1 episodes overlapping a sensor-floor run, per patient
    l2_pp: dict[str, dict[str, int]] = {"T": {}, "E": {}}

    for rec, lab in labelled:
        pid = rec.identity.patient_id
        s = lab.series
        plab = lab.prediction
        for lv, eps in (("L1", lab.l1), ("L2", lab.l2), ("L1_single", lab.l1_single)):
            per_patient[pid][lv] += len(eps)
            for e in eps:
                end_reasons[lv][e.end_reason.value] += 1
                durations[lv].append(e.duration_s / 60)
                nadirs[lv].append(e.nadir_mgdl)
        if partition.get(pid) in l2_pp:
            l2_pp[partition[pid]][pid] = l2_pp[partition[pid]].get(pid, 0) + len(lab.l2)
        # --- L1 annotations, boundaries, spacing ---
        runs = floor_runs(s.ts, s.value, cfg.max_step_s)
        sensor_runs["recordings_with_run"] += int(bool(runs))
        sensor_runs[f"recordings_with_run_{partition.get(pid, '?')}"] += int(bool(runs))
        for e in lab.l1:
            a = annotate(e, s.ts, s.value, utc_offset_s, runs)
            ann["sensor_floor_run"] += a.sensor_floor_run
            flagged_pp[pid] += a.sensor_floor_run
            ann["nocturnal_00_06"] += a.nocturnal
            ann["within_first_24h"] += a.within_first_24h
            ann["compression_candidates"] += a.compression_candidate
            ann["prior_reading_lt80"] += a.prior_reading_lt80
            hours[a.onset_local_hour] += 1
            edge["onset_within_first_2h"] += int(e.onset_ts - s.ts[0] < cfg.min_time_since_start_s)
            edge["onset_within_last_60min"] += int(s.ts[-1] - e.onset_ts < cfg.horizon_s)
        on = [e.onset_ts for e in lab.l1]
        inter_onset_min += [(b - a) / 60 for a, b in pairwise(on)]
        end_to_next_min += [
            (n.onset_ts - e.end_ts) / 60
            for e, n in zip(lab.l1, lab.l1[1:], strict=False)
            if e.end_ts is not None
        ]
        # --- prediction times ---
        reasons.update(Ineligibility(int(c)).name for c in plab.reason)
        pred["readings"] += len(plab.ts)
        pred["eligible"] += int(plab.eligible.sum())
        pred["positive"] += int((plab.y == 1).sum())
        if len(plab.ts):
            coverage.append(float(plab.eligible.mean()))
        onsets = np.array(on, dtype=np.int64)
        warn["blueprint"] += int(warnable_onsets(plab, onsets, cfg).sum())
        warn["legacy"] += int(legacy_warnable(plab, onsets, cfg.horizon_s).sum())
        # --- legacy treatment (recording level) ---
        t = legacy_treatment(rec)
        treat_rec[rec.identity.recording_key] = t
        for _ in lab.l1:
            l1_rec_class["insulin"] += t.insulin_any
            l1_rec_class["secretagogue"] += t.secretagogue_any
            l1_rec_class["either"] += t.insulin_any or t.secretagogue_any
            l1_rec_class["neither"] += not (t.insulin_any or t.secretagogue_any)
        # --- label validity ---
        cbg = cbg_series(rec)
        c_b, c_g = pair_cbg_cgm(cbg, s.ts, s.value, int(g3b["pair_window_min"]) * 60)
        pairs_cbg.append(c_b)
        pairs_cgm.append(c_g)
        for e in lab.l1:
            st = episode_cbg_status(
                e, cbg, int(g3b["episode_cbg_tail_min"]) * 60, cfg.l1_threshold_mgdl
            )
            during["with_cbg"] += st is not None
            during["confirmed"] += st is True
            during["contradicted"] += st is False
            ow = episode_cbg_status_onset_window(e, cbg, cfg.l1_threshold_mgdl)
            onset_window["confirmed"] += ow is True
            onset_window["unconfirmed"] += ow is False
            onset_window["no_cbg"] += ow is None

    # --- patient-level treatment and partition aggregates ---
    treated = {pid: False for pid in patients}
    treated_strict = {pid: False for pid in patients}
    iv_only = 0
    for rec, _ in labelled:
        t = treat_rec[rec.identity.recording_key]
        pid = rec.identity.patient_id
        treated[pid] |= t.insulin_any or t.secretagogue_any
        treated_strict[pid] |= t.insulin_strict or t.secretagogue_any
    iv_only = sum(1 for p in patients if treated[p] != treated_strict[p])
    l1 = {p: per_patient[p]["L1"] for p in patients}
    by_part: dict[str, Any] = {}
    strata: Counter[str] = Counter()
    for part in ("T", "E"):
        members = [p for p in patients if partition.get(p) == part]
        tr = [p for p in members if treated[p]]
        by_part[part] = {
            "patients": len(members),
            "patients_with_L1": sum(1 for p in members if l1[p] > 0),
            "L1": sum(l1[p] for p in members),
            "treated_patients": len(tr),
            "treated_L1": sum(l1[p] for p in tr),
            "treated_with_L1": sum(1 for p in tr if l1[p] > 0),
            "treated_m_w": m_w([l1[p] for p in tr]),
            "L1_concentration": {
                k: v
                for k, v in _per_patient_summary({p: l1[p] for p in members}, members).items()
                if k in ("top1_share", "top5_share", "m_w")
            },
            "L2": {
                k: v
                for k, v in _per_patient_summary(l2_pp[part], members).items()
                if k in ("episodes", "patients_with", "top1_share", "top5_share", "m_w")
            },
            "L1_overlapping_sensor_floor_run": sum(flagged_pp[p] for p in members),
            "treated_L1_overlapping_sensor_floor_run": sum(flagged_pp[p] for p in tr),
        }
        for p in members:
            strata[f"{part}:{int(treated[p]) * 2 + int(l1[p] > 0)}"] += 1
    missing_partition = sorted(p for p in patients if p not in partition)

    pc = np.concatenate(pairs_cbg) if pairs_cbg else np.zeros(0)
    pg = np.concatenate(pairs_cgm) if pairs_cgm else np.zeros(0)
    agree = agreement_stats(pc, pg, cfg.l1_threshold_mgdl)
    n_l1 = sum(l1.values())
    levels = {
        lv: {
            **_per_patient_summary({p: per_patient[p][lv] for p in patients}, patients),
            "end_reasons": dict(sorted(end_reasons[lv].items())),
            "duration_min_q1_median_q3": _q(durations[lv], [25, 50, 75]),
            "duration_min_min_max": (
                [round(min(durations[lv]), 1), round(max(durations[lv]), 1)]
                if durations[lv]
                else None
            ),
            "nadir_median": round(float(np.median(nadirs[lv])), 1) if nadirs[lv] else None,
        }
        for lv in LEVELS
    }
    patients_treated = sum(treated.values())

    results: dict[str, Any] = {
        "label_config": cfg.as_dict(),
        "label_config_sha256": cfg.sha256,
        "recordings": len(recs),
        "patients": len(patients),
        "episodes": levels,
        "single_to_L1_ratio": round(levels["L1_single"]["episodes"] / n_l1, 3) if n_l1 else None,
        "L1_annotations": dict(sorted(ann.items())),
        "sensor_floor_runs": dict(sorted(sensor_runs.items())),
        "L1_onset_local_hour": {str(h): hours[h] for h in range(24) if hours[h]},
        "L1_boundaries": dict(sorted(edge.items())),
        "L1_spacing": {
            "inter_onset_min_q1_median_q3": _q(inter_onset_min, [25, 50, 75]),
            "inter_onset_lt_120min": sum(1 for x in inter_onset_min if x < 120),
            "end_to_next_onset_min_min_median": (
                [round(min(end_to_next_min), 1), round(float(np.median(end_to_next_min)), 1)]
                if end_to_next_min
                else None
            ),
            "next_onset_within_refractory": sum(
                1 for x in end_to_next_min if x < cfg.refractory_s / 60
            ),
        },
        "L1_warnable": {
            "blueprint_definition": warn["blueprint"],
            "legacy_definition": warn["legacy"],
            "warnable_share": round(warn["blueprint"] / n_l1, 3) if n_l1 else None,
        },
        "prediction_times": {
            "readings": pred["readings"],
            "eligible": pred["eligible"],
            "positive": pred["positive"],
            "prevalence": round(pred["positive"] / pred["eligible"], 4)
            if pred["eligible"]
            else None,
            "eligible_share_of_readings": (
                round(pred["eligible"] / pred["readings"], 4) if pred["readings"] else None
            ),
            "ineligibility_reasons": {k: reasons[k] for k in sorted(reasons)},
            "per_recording_eligible_share_min_median_max": _q(coverage, [0, 50, 100]),
        },
        "treatment_legacy_provisional": {
            "definition": "Blueprint audit.py rule (any matched s.c. insulin class, any CSII cell, "
            "any i.v. cell, or an oral SU/glinide); PROVISIONAL until the S3 parser",
            "patients_treated": patients_treated,
            "patients_treated_strict_iv": sum(treated_strict.values()),
            "patients_status_depends_on_non_insulin_iv": iv_only,
            "L1_in_treated_recordings": l1_rec_class["either"],
            "L1_in_insulin_recordings": l1_rec_class["insulin"],
            "L1_in_secretagogue_recordings": l1_rec_class["secretagogue"],
            "L1_in_neither": l1_rec_class["neither"],
            "treated_m_w_all": m_w([l1[p] for p in patients if treated[p]]),
        },
        "by_partition": by_part,
        "strata_counts": dict(sorted(strata.items())),
        "patients_missing_from_partition": len(missing_partition),
        "label_validity": {
            **agree,
            "L1_with_cbg_during": during["with_cbg"],
            "L1_cbg_during_confirmed": during["confirmed"],
            "L1_cbg_during_contradicted": during["contradicted"],
            "unconfirmed_share": (
                round(1 - during["confirmed"] / during["with_cbg"], 3)
                if during["with_cbg"]
                else None
            ),
            "legacy_onset_window": dict(sorted(onset_window.items())),
        },
    }
    results["blueprint_definitions"] = blueprint_definitions(results)
    return results


def blueprint_definitions(r: dict[str, Any]) -> dict[str, Any]:
    """Flat values under the blueprint audit's definitions (keys = audit_summary JSON keys)."""
    l1, l2, s1 = r["episodes"]["L1"], r["episodes"]["L2"], r["episodes"]["L1_single"]
    tr, lv, bp = r["treatment_legacy_provisional"], r["label_validity"], r["by_partition"]
    return {
        "L1_episodes": l1["episodes"],
        "L2_episodes": l2["episodes"],
        "L1_single_reading": s1["episodes"],
        "patients_with_L1": l1["patients_with"],
        "patients_with_L2": l2["patients_with"],
        "patients_with_L1_single": s1["patients_with"],
        "L1_top5_counts": l1["top5_counts"],
        "L1_top5_patients_share": l1["top5_share"],
        "L1_end_reason": l1["end_reasons"],
        "L1_duration_min_median": (l1["duration_min_q1_median_q3"] or [None] * 3)[1],
        "L1_nadir_median": l1["nadir_median"],
        "L1_nocturnal_00_06": r["L1_annotations"].get("nocturnal_00_06", 0),
        "L1_within_first_24h": r["L1_annotations"].get("within_first_24h", 0),
        "L1_prior_reading_lt80": r["L1_annotations"].get("prior_reading_lt80", 0),
        "L1_warnable_h60": r["L1_warnable"]["legacy_definition"],
        "episodes_suspect_artefact": r["L1_annotations"].get("compression_candidates", 0),
        "eligible_points_h60": r["prediction_times"]["eligible"],
        "positive_points_h60": r["prediction_times"]["positive"],
        "patients_insulin_or_secretagogue": tr["patients_treated"],
        "L1_in_insulin_or_secretagogue_recordings": tr["L1_in_treated_recordings"],
        "L1_in_insulin_recordings": tr["L1_in_insulin_recordings"],
        "L1_in_secretagogue_recordings": tr["L1_in_secretagogue_recordings"],
        "L1_in_neither": tr["L1_in_neither"],
        "T_L1": bp["T"]["L1"],
        "T_L1_treated": bp["T"]["treated_L1"],
        "T_treated_with_L1": bp["T"]["treated_with_L1"],
        "T_treated_m_w": bp["T"]["treated_m_w"],
        "E_L1": bp["E"]["L1"],
        "E_L1_treated": bp["E"]["treated_L1"],
        "E_treated_with_L1": bp["E"]["treated_with_L1"],
        "E_treated_m_w": bp["E"]["treated_m_w"],
        "T_treated": bp["T"]["treated_patients"],
        "E_treated": bp["E"]["treated_patients"],
        "treated_m_w_all": tr["treated_m_w_all"],
        "cbg_cgm_pairs": lv.get("pairs"),
        "cgm_minus_cbg_mean": lv.get("cgm_minus_cbg_mean"),
        "cgm_minus_cbg_median": lv.get("cgm_minus_cbg_median"),
        "mard_pct": lv.get("mard_pct"),
        "pairs_cbg_lt100": lv.get("pairs_cbg_lt100"),
        "cgm_minus_cbg_mean_cbg_lt100": lv.get("cgm_minus_cbg_mean_cbg_lt100"),
        "pairs_cgm_lt70": lv.get("pairs_cgm_lt70"),
        "pairs_cgm_lt70_cbg_lt70": lv.get("pairs_cgm_lt70_cbg_lt70"),
        "pairs_cbg_lt70": lv.get("pairs_cbg_lt70"),
        "episodes_with_cbg_during": lv["L1_with_cbg_during"],
        "episodes_cbg_during_lt70": lv["L1_cbg_during_confirmed"],
        "L1_cbg_confirmed": lv["legacy_onset_window"].get("confirmed", 0),
        "L1_cbg_unconfirmed": lv["legacy_onset_window"].get("unconfirmed", 0),
        "L1_no_cbg_nearby": lv["legacy_onset_window"].get("no_cbg", 0),
    }


__all__ = ["Episode", "blueprint_definitions", "m_w", "measure_events"]
