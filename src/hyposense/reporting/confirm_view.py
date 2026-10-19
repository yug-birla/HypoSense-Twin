"""Read-only summary of a confirmatory results document (S9) for the Evidence View, the README
and the model card. It only selects and labels frozen numbers; it computes nothing new.

The same function also formats a REHEARSAL document (T only) so that the presentation path is
tested before freeze. The status field always comes from the document itself.
"""

from __future__ import annotations

from typing import Any

PRIMARY_CONTRAST = "preview_M3-M2:sens1"
ANALYSES: tuple[tuple[str, str, str], ...] = (
    # key, group, description (ANALYSIS_PLAN §5.7 items 13-27)
    ("primary", "Primary", "E-treated, sens@1FA (H1 population)"),
    ("S6_all_patients", "Secondary", "S6 all evaluation patients"),
    ("S1_lead30", "Secondary", "S1 minimum lead 30 min"),
    ("S5_L2", "Secondary", "S5 level-2 episodes (< 54 mg/dL)"),
    ("SA1_single_reading", "Sensitivity", "SA1 single-reading event definition"),
    ("SA2_first24h", "Sensitivity", "SA2 first 24 h of each recording"),
    ("SA3_no_pump_iv", "Sensitivity", "SA3 without pump / IV insulin"),
    ("SA4_compression", "Sensitivity", "SA4 suspected compression lows excluded"),
    ("SA5_cbg_contradicted", "Sensitivity", "SA5 CBG-contradicted episodes excluded"),
    ("SA6_x0.75", "Sensitivity", "SA6 kernel durations x 0.75"),
    ("SA6_x1.5", "Sensitivity", "SA6 kernel durations x 1.5"),
    ("SA7_seed2028", "Sensitivity", "SA7 fold seed 2028"),
    ("SA7_seed2029", "Sensitivity", "SA7 fold seed 2029"),
    ("SA7_seed2030", "Sensitivity", "SA7 fold seed 2030"),
    ("SA7_seed2031", "Sensitivity", "SA7 fold seed 2031"),
    ("SA7_seed2032", "Sensitivity", "SA7 fold seed 2032"),
    ("SA8", "Sensitivity", "SA8 without laboratory features"),
    ("SA9_sensor_floor", "Sensitivity", "SA9 sensor-floor windows excluded"),
    ("PB6", "Sensitivity", "P-B6 training-exclusion mask"),
    ("R1_30min", "Robustness", "R1 dose times jittered ±30 min"),
    ("R1_60min", "Robustness", "R1 dose times jittered ±60 min"),
    ("R2_random10", "Robustness", "R2 10 % CGM removed at random"),
    ("R2_random20", "Robustness", "R2 20 % CGM removed at random"),
    ("R2_block10", "Robustness", "R2 10 % CGM removed in blocks"),
    ("R2_block20", "Robustness", "R2 20 % CGM removed in blocks"),
    ("R3", "Robustness", "R3 logistic regression learner"),
    ("R4", "Robustness", "R4 per-model hyperparameters"),
)
LADDER = ("M0", "M1", "M2", "M3r", "M3")


def _point(d: dict[str, Any] | None) -> float | None:
    return None if d is None else d.get("point")


def _ci(d: dict[str, Any] | None) -> list[float] | None:
    return None if d is None else d.get("ci95")


def pending_view() -> dict[str, Any]:
    return {
        "status": "PENDING",
        "note": (
            "The sealed evaluation partition (E) has not been opened. The confirmatory run "
            "executes once, after the protocol freeze (ANALYSIS_PLAN §5.7)."
        ),
    }


def confirmatory_view(doc: dict[str, Any]) -> dict[str, Any]:
    """`doc` is a results.json document of `hyposense confirm` (official or rehearsal)."""
    r = doc["results"]
    ev = r["evaluations"]
    rows = []
    for key, group, label in ANALYSES:
        e = ev.get(key)
        if e is None:
            rows.append({"key": key, "group": group, "label": label, "available": False})
            continue
        iv, cp = e.get("intervals", {}), e.get("comparisons", {})
        rows.append(
            {
                "key": key,
                "group": group,
                "label": label,
                "available": True,
                "patients": e.get("patients"),
                "episodes": e.get("episodes"),
                "M2_sens1": _point(iv.get("M2:sens1")),
                "M3_sens1": _point(iv.get("M3:sens1")),
                "delta": _point(cp.get(PRIMARY_CONTRAST)),
                "delta_ci95": _ci(cp.get(PRIMARY_CONTRAST)),
                "logloss_delta": _point(cp.get("preview_M3-M2:logloss")),
            }
        )
    prim = ev["primary"]
    ladder = {
        m: {
            "sens1": _point(prim["intervals"].get(f"{m}:sens1")),
            "sens1_ci95": _ci(prim["intervals"].get(f"{m}:sens1")),
            "logloss": _point(prim["intervals"].get(f"{m}:logloss")),
        }
        for m in LADDER
    }
    contrasts = {
        k.split(":")[0]: {"point": v["point"], "ci95": v["ci95"]}
        for k, v in prim["comparisons"].items()
        if k.endswith(":sens1")
    }
    deployed = {
        m: {
            k: v.get(k)
            for k in ("sensitivity", "fa_per_day", "alert_precision", "episodes", "hits")
        }
        | {"lead_median_min": (v.get("lead_min") or {}).get("median")}
        for m, v in r["deployed_operating_point"].items()
    }
    return {
        "status": r["status"],
        "run_id": doc["run_id"],
        "results_sha256": doc["results_sha256"],
        "freeze": r.get("freeze"),
        "commit": (doc.get("provenance") or {}).get("git", {}).get("commit"),
        "population": r["population"],
        "primary": r["primary"],
        "ladder": ladder,
        "contrasts": contrasts,
        "s2_matched_sensitivity_fa_delta": r["S2_matched_sensitivity_fa_delta"],
        "selection": r["model_selection"],
        "interpretation": r["interpretation_table_20_4"],
        "deployed_operating_point": deployed,
        "analyses": rows,
        "demo_cases": r["demo_cases"],
    }
