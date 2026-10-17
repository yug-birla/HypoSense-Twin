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
