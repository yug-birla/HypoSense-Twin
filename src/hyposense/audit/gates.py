"""Machine-readable evidence gates G0 (source integrity) and G1 (dataset usability).

Blueprint Table 21.1:
- G0: official copy downloaded; SHA-256; file and reading counts vs descriptor. Accept: 109
  files; CGM count reconciled to 112,475 or the difference explained. Fail → block unsealing E.
- G1: parse rate and interval distribution. Accept: >=99% of readings parse; >=99% of intervals
  <=20 min. Fail → stop.

The evaluation functions are pure (inputs → result dict). Writing to disk is separate.
Thresholds come from configs/default.yaml `gates` (Class C, locked by the constant test).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hyposense.common.config import REPO_ROOT

PASS, PARTIAL, FAIL, INFO = "PASS", "PARTIAL", "FAIL", "INFO"


def gates_dir() -> Path:
    return REPO_ROOT / "artifacts" / "gates"


def _check(
    cid: str, status: str, summary: str, measured: Any = None, criterion: Any = None
) -> dict[str, Any]:
    return {
        "id": cid,
        "status": status,
        "summary": summary,
        "measured": measured,
        "criterion": criterion,
    }


def _overall(checks: list[dict[str, Any]]) -> str:
    statuses = {c["status"] for c in checks}
    if FAIL in statuses:
        return FAIL
    if PARTIAL in statuses:
        return PARTIAL
    return PASS


def evaluate_g0(
    *,
    archive_record: dict[str, Any],
    pinned: dict[str, Any],
    canonical_version: int,
    archive_verified: bool,
    manifest_verified: bool,
    measured: dict[str, Any],
    expected: dict[str, Any],
    published_cgm: int,
    noted_recordings: list[str],
    reconciliation: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    checks = []
    src_ok = (
        archive_record.get("source") == "figshare"
        and archive_record.get("version") == canonical_version
        and archive_record.get("file_id") == pinned["file_id"]
    )
    checks.append(
        _check(
            "G0.1-official-source",
            PASS if src_ok else FAIL,
            f"figshare article version {archive_record.get('version')} "
            f"(file {archive_record.get('file_id')})",
            archive_record.get("version_doi"),
            f"figshare canonical version {canonical_version}",
        )
    )
    prov_fields = ("retrieved_utc", "version_doi", "md5", "sha256", "url", "licence")
    missing = [f for f in prov_fields if not archive_record.get(f)]
    checks.append(
        _check(
            "G0.2-provenance-recorded",
            FAIL if missing else PASS,
            "retrieval date, DOI, checksums, URL and licence recorded"
            if not missing
            else f"missing provenance fields {missing}",
            {f: archive_record.get(f) for f in prov_fields},
        )
    )
    checks.append(
        _check(
            "G0.3-archive-checksum",
            PASS if archive_verified else FAIL,
            "archive matches figshare MD5 and pinned SHA-256"
            if archive_verified
            else "archive checksum mismatch",
            {"md5": archive_record.get("md5"), "sha256": archive_record.get("sha256")},
            {"md5": pinned["md5"], "sha256": pinned.get("sha256")},
        )
    )
    checks.append(
        _check(
            "G0.4-manifest",
            PASS if manifest_verified else FAIL,
            "every extracted file matches data/MANIFEST.json"
            if manifest_verified
            else "manifest verification failed",
            measured.get("manifest_files_sha256"),
        )
    )
    files_ok = (
        measured["recording_files"] == expected["expected_recording_files"]
        and measured["summary_present"]
    )
    checks.append(
        _check(
            "G0.5-file-count",
            PASS if files_ok else FAIL,
            f"{measured['recording_files']} recording files + summary",
            measured["recording_files"],
            expected["expected_recording_files"],
        )
    )
    rp_ok = (
        measured["recordings"] == expected["expected_recording_files"]
        and measured["patients"] == expected["expected_patients"]
    )
    checks.append(
        _check(
            "G0.6-recordings-patients",
            PASS if rp_ok else FAIL,
            f"{measured['recordings']} recordings / {measured['patients']} patients",
            [measured["recordings"], measured["patients"]],
            [expected["expected_recording_files"], expected["expected_patients"]],
        )
    )
    cgm, rows = measured["cgm_readings"], measured["rows"]
    no_cgm = measured["rows_without_cgm_by_recording"]
    if cgm == published_cgm:
        st, msg = PASS, f"CGM readings {cgm} equal the published {published_cgm}"
    elif rows == published_cgm and set(no_cgm) <= set(noted_recordings):
        st = PASS
        msg = (
            f"MEASURED: published {published_cgm} equals the number of timepoint rows; "
            f"{rows - cgm} rows carry no CGM value, all in {sorted(no_cgm)}, which the "
            "publisher's v5 note documents (CGM device replaced). Non-empty CGM readings: "
            f"{cgm}. INFERRED: the descriptor's figure counts timepoint rows. "
            "Difference explained."
        )
    else:
        st, msg = (
            PARTIAL,
            (
                f"CGM readings {cgm} (rows {rows}) vs published {published_cgm}: "
                "UNEXPLAINED — E must not be unsealed until resolved"
            ),
        )
    checks.append(
        _check(
            "G0.7-published-count-reconciled",
            st,
            msg,
            {"cgm_readings": cgm, "rows": rows, "rows_without_cgm": no_cgm},
            published_cgm,
        )
    )
    if reconciliation is None:
        checks.append(
            _check("G0.8-blueprint-mirror-reconciled", PARTIAL, "version reconciliation skipped")
        )
    else:
        unexplained = [
            r["metric"] for r in reconciliation if r["status"] == "UNEXPLAINED DIFFERENCE"
        ]
        counts: dict[str, int] = {}
        for r in reconciliation:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        checks.append(
            _check(
                "G0.8-blueprint-mirror-reconciled",
                PARTIAL if unexplained else PASS,
                f"structural blueprint values: {counts}"
                + (f"; unexplained: {unexplained}" if unexplained else ""),
                counts,
                "no UNEXPLAINED DIFFERENCE",
            )
        )
    discrepancies = [c for c in checks if c["status"] != PASS]
    return {
        "gate": "G0",
        "title": "Source integrity",
        "status": _overall(checks),
        "checks": checks,
        "discrepancies": [c["id"] for c in discrepancies],
        "consequence_if_not_pass": "E must not be unsealed (Blueprint Table 21.1)",
    }


def evaluate_g1(*, measured: dict[str, Any], criteria: dict[str, Any]) -> dict[str, Any]:
    pr = measured["cgm_parse_rate"]
    ir = measured["interval_le_max_rate"]
    checks = [
        _check(
            "G1.1-cgm-parse-rate",
            PASS if pr is not None and pr >= criteria["min_cgm_parse_rate"] else FAIL,
            f"{measured['cgm_parsed']}/{measured['cgm_cells_nonempty']} non-empty CGM cells "
            "parse to a finite value with a valid timestamp",
            pr,
            f">= {criteria['min_cgm_parse_rate']}",
        ),
        _check(
            "G1.2-interval-rate",
            PASS if ir is not None and ir >= criteria["min_interval_le_rate"] else FAIL,
            f"share of consecutive-reading intervals <= {criteria['max_interval_min']} min "
            f"({measured['cgm_intervals']} intervals)",
            ir,
            f">= {criteria['min_interval_le_rate']}",
        ),
        _check(
            "G1.3-timestamp-parse",
            INFO,
            "rows with a valid timestamp",
            measured["timestamp_parse_rate"],
        ),
        _check(
            "G1.4-duplicates",
            INFO,
            "duplicate-timestamp and exact-duplicate rows",
            measured["duplicates"],
        ),
        _check(
            "G1.5-critical-fields",
            INFO,
            "recordings missing Date or CGM columns (the loader refuses such files)",
            0,
        ),
        _check(
            "G1.6-invalid-cgm",
            INFO,
            "CGM values unparseable or outside [20, 600] mg/dL",
            measured["invalid_cgm"],
        ),
        _check(
            "G1.7-structural-anomalies", INFO, "loader issues by severity:code", measured["issues"]
        ),
    ]
    gating = [c for c in checks if c["status"] != INFO]
    status = FAIL if any(c["status"] == FAIL for c in gating) else PASS
    return {
        "gate": "G1",
        "title": "Dataset usability",
        "status": status,
        "checks": checks,
        "discrepancies": [c["id"] for c in gating if c["status"] != PASS],
        "consequence_if_not_pass": "STOP: change dataset (Blueprint Table 21.1)",
    }


def write_gate(
    result: dict[str, Any], provenance: dict[str, Any], evidence: dict[str, str], evaluated_utc: str
) -> Path:
    out = gates_dir() / f"{result['gate']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {**result, "evaluated_utc": evaluated_utc, "evidence": evidence, "provenance": provenance}
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------------------------------------
# G2 · Event sufficiency (Blueprint Table 21.1, §8.6, Table 8.4)
# ---------------------------------------------------------------------------------------------

Z_975 = 1.959964  # two-sided 95 %
Z_80 = 0.841621  # 80 % power


def precision_table(
    episodes: int, m_w: float, p: float, icc_grid: list[float]
) -> list[dict[str, Any]]:
    """Design effect 1 + (m_w - 1) * ICC; effective n = episodes / DE; 95 % CI half-width of a
    sensitivity p (normal approximation); minimum detectable paired difference at 80 % power for
    discordance 15 % / 25 % (sqrt(d / n_eff) * (z_.975 + z_.80)). Reproduces Blueprint Table 8.4."""
    rows = []
    for icc in icc_grid:
        de = 1 + (m_w - 1) * icc
        n_eff = episodes / de
        rows.append(
            {
                "icc": icc,
                "design_effect": round(de, 2),
                "effective_n": round(n_eff, 1),
                "ci_half_width": round(Z_975 * (p * (1 - p) / n_eff) ** 0.5, 3),
                "mdd_discordance_15": round((Z_975 + Z_80) * (0.15 / n_eff) ** 0.5, 3),
                "mdd_discordance_25": round((Z_975 + Z_80) * (0.25 / n_eff) ** 0.5, 3),
            }
        )
    return rows


def evaluate_g2(
    *, measured: dict[str, Any], criteria: dict[str, Any], provisional_reasons: list[str]
) -> dict[str, Any]:
    eps, pts, mw = (
        measured["E_treated_L1"],
        measured["E_treated_with_L1"],
        measured["E_treated_m_w"],
    )
    table = precision_table(eps, mw, criteria["p_ref"], list(criteria["icc_grid"]))
    ref = next(r for r in table if abs(r["icc"] - criteria["icc_ref"]) < 1e-12)
    checks = [
        _check(
            "G2.1-episodes",
            PASS if eps >= criteria["min_episodes"] else FAIL,
            f"{eps} L1 episodes in E-treated patients",
            eps,
            f">= {criteria['min_episodes']}",
        ),
        _check(
            "G2.2-patients",
            PASS if pts >= criteria["min_patients_with_episode"] else FAIL,
            f"{pts} E-treated patients with >= 1 L1 episode",
            pts,
            f">= {criteria['min_patients_with_episode']}",
        ),
        _check(
            "G2.3-precision",
            PASS if ref["ci_half_width"] <= criteria["max_ci_half_width"] else FAIL,
            f"95% CI half-width {ref['ci_half_width']} at ICC {criteria['icc_ref']}, "
            f"p = {criteria['p_ref']}, m_w = {mw}",
            ref["ci_half_width"],
            f"<= {criteria['max_ci_half_width']}",
        ),
        _check(
            "G2.4-precision-table",
            INFO,
            "Blueprint Table 8.4 reproduced from measured values",
            table,
        ),
        _check(
            "G2.5-all-patient-fallback",
            INFO,
            "E all patients (fallback population if G2 fails)",
            measured.get("E_all"),
        ),
    ]
    gating = [c for c in checks if c["status"] != INFO]
    status = FAIL if any(c["status"] == FAIL for c in gating) else PASS
    return {
        "gate": "G2",
        "title": "Event sufficiency",
        "status": status,
        "checks": checks,
        "discrepancies": [c["id"] for c in gating if c["status"] != PASS],
        "conditions": provisional_reasons,
        "assumptions": [
            "ICC of the warned/missed outcome is unknown; Blueprint uses 0.05-0.30 "
            "(reference 0.15)",
            "normal approximation; confirmatory intervals use the patient-cluster bootstrap",
        ],
        "consequence_if_not_pass": "All patients as primary population; else descriptive claim "
        "only (Blueprint Table 21.1)",
    }


# ---------------------------------------------------------------------------------------------
# G3b · Label validity (Blueprint Table 21.1, §8.4)
# ---------------------------------------------------------------------------------------------

TRIGGERED = "TRIGGERED"


def evaluate_g3b(*, measured: dict[str, Any], criteria: dict[str, Any]) -> dict[str, Any]:
    with_cbg, confirmed = measured["L1_with_cbg_during"], measured["L1_cbg_during_confirmed"]
    if with_cbg == 0:
        status, msg = (
            FAIL,
            "no L1 episode has a concurrent capillary value; validity not assessable",
        )
        share = None
    else:
        share = round(1 - confirmed / with_cbg, 3)
        status = TRIGGERED if share > criteria["max_unconfirmed_share"] else PASS
        msg = (
            f"{with_cbg - confirmed}/{with_cbg} L1 episodes with a concurrent CBG were not "
            f"confirmed < 70 mg/dL (unconfirmed share {share})"
        )
    checks = [
        _check(
            "G3b.1-episode-confirmation",
            status,
            msg,
            share,
            f"unconfirmed share <= {criteria['max_unconfirmed_share']} -> PASS; above -> TRIGGERED",
        ),
        _check(
            "G3b.2-agreement",
            INFO,
            "CGM vs CBG pairs within +/- 8 min",
            {
                k: measured.get(k)
                for k in (
                    "pairs",
                    "cgm_minus_cbg_mean",
                    "cgm_minus_cbg_median",
                    "cgm_minus_cbg_sd",
                    "mard_pct",
                    "cgm_minus_cbg_mean_cbg_lt100",
                )
            },
        ),
        _check(
            "G3b.3-low-range-discordance",
            INFO,
            "agreement around 70 mg/dL (both directions)",
            {
                k: measured.get(k)
                for k in (
                    "pairs_cgm_lt70",
                    "pairs_cgm_lt70_cbg_lt70",
                    "pairs_cbg_lt70",
                    "pairs_cbg_lt70_cgm_lt70",
                )
            },
        ),
        _check(
            "G3b.4-sensor-artefacts",
            INFO,
            "episodes overlapping >= 2 h at the sensor floor (P-C8 candidate flag)",
            measured.get("sensor_floor_run"),
        ),
    ]
    consequences = (
        [
            "target named 'CGM-detected L1 episode' (never 'hypoglycaemia' without qualification)",
            "SA5: primary comparison repeated excluding episodes contradicted by a concurrent CBG",
            "clinical action = capillary glucose check, not treatment",
            "L2 reported as a secondary endpoint",
        ]
        if status == TRIGGERED
        else []
    )
    return {
        "gate": "G3b",
        "title": "Label validity",
        "status": status,
        "checks": checks,
        "consequences_applied": consequences,
        "discrepancies": [c["id"] for c in checks if c["status"] not in (PASS, INFO)],
        "consequence_if_not_pass": "Rename label, run SA5, capillary-check action "
        "(Blueprint Table 21.1)",
    }


# ---------------------------------------------------------------------------------------------
# G3 · Medication usability (Blueprint Table 21.1)
# ---------------------------------------------------------------------------------------------


def evaluate_g3(*, measured: dict[str, Any], criteria: dict[str, Any]) -> dict[str, Any]:
    pr, cov = measured["parse_rate"], measured["day_coverage_median"]
    res = measured["timing_resolution_min"]
    var = measured["treated_E_patients_with_exposure_variation"]
    grid = measured["timing_on_grid_rate"]
    checks = [
        _check(
            "G3.1-parse-rate",
            PASS if pr is not None and pr >= criteria["min_parse_rate"] else FAIL,
            "target administrations (insulin, SU, glinide) parsed to drug + dose, among all "
            "target administrations plus unrecognised/ambiguous entries",
            pr,
            f">= {criteria['min_parse_rate']}",
        ),
        _check(
            "G3.2-day-coverage",
            PASS if cov is not None and cov >= criteria["min_day_coverage"] else FAIL,
            "median share of CGM calendar days with >= 1 target administration, over treated "
            "recordings",
            cov,
            f">= {criteria['min_day_coverage']}",
        ),
        _check(
            "G3.3-timing-resolution",
            PASS
            if res <= criteria["max_timing_resolution_min"] and grid is not None and grid >= 0.99
            else FAIL,
            f"administration timestamps lie on the 15-min CGM grid (share {grid})",
            res,
            f"<= {criteria['max_timing_resolution_min']} min",
        ),
        _check(
            "G3.4-treated-E-with-variation",
            PASS if var >= criteria["min_treated_E_patients_with_variation"] else FAIL,
            "E-treated patients with >= 2 distinct target administration times (exposure "
            "necessarily varies)",
            var,
            f">= {criteria['min_treated_E_patients_with_variation']}",
        ),
    ]
    status = FAIL if any(c["status"] == FAIL for c in checks) else PASS
    return {
        "gate": "G3",
        "title": "Medication usability",
        "status": status,
        "checks": checks,
        "discrepancies": [c["id"] for c in checks if c["status"] != PASS],
        "consequence_if_not_pass": "Context-only branch (M2 vs M1) (Blueprint Table 21.1)",
    }
