"""`hyposense audit run`: structural audit → version reconciliation → blueprint reconciliation
→ G0/G1, written with full provenance.

Outputs:
- experiments/runs/<run_id>/audit_structural.json   (provenance + deterministic results)
- experiments/runs/<run_id>/audit_structural.md     (human-readable summary)
- artifacts/gates/G0.json, artifacts/gates/G1.json  (latest gate evaluations)

`results_sha256` hashes only the deterministic content (results, version reconciliation and
blueprint reconciliation). Two runs over the same data, code and config give the same value.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hyposense.audit.gates import evaluate_g0, evaluate_g1, write_gate
from hyposense.audit.reconcile import reconcile
from hyposense.audit.structural import measure
from hyposense.audit.versions import reconcile_versions
from hyposense.common.config import CONFIG_DIR, REPO_ROOT, config_hash, load_config, load_yaml
from hyposense.common.hashing import sha256_json
from hyposense.common.provenance import environment, git_state, make_run_id, utc_now_iso
from hyposense.data.dataset import AccessScope, load_dataset
from hyposense.data.manifest import ChecksumError
from hyposense.data.quality import QualityThresholds
from hyposense.data.source import (
    SourceIntegrityError,
    archive_path,
    archive_spec,
    dataset_config,
    verify_archive,
)


def thresholds_from_config(cfg: dict[str, Any]) -> QualityThresholds:
    p = cfg["policy"]
    return QualityThresholds(
        max_gap_min=float(p["max_gap_min"]),
        floor_mgdl=float(p["floor_mgdl"]),
        max_rate_mgdl_per_min=float(p["max_rate_mgdl_per_min"]),
        warmup_min=float(p["warmup_min"]),
    )


def run_audit(*, skip_versions: bool = False) -> dict[str, Any]:
    cfg, dcfg = load_config(), dataset_config()
    started = utc_now_iso()
    spec = archive_spec(None, dcfg)
    apath = archive_path(spec, dcfg)
    try:
        verify_archive(apath, spec)
        archive_ok = True
    except (SourceIntegrityError, FileNotFoundError):
        archive_ok = False
    record = json.loads(apath.with_suffix(".provenance.json").read_text(encoding="utf-8"))

    try:
        ds = load_dataset(AccessScope.AGGREGATE_AUDIT)
        manifest_ok = True
    except ChecksumError:
        manifest_ok = False
        raise
    thr = thresholds_from_config(cfg)
    max_iv = float(cfg["gates"]["g1"]["max_interval_min"])
    results = measure(ds.recordings, ds.summary, thr, max_iv)
    results["timestamps"]["assumed_utc_offset"] = cfg["time"]["assumed_utc_offset"]
    offset = str(cfg["time"]["assumed_utc_offset"])
    versions = (
        None
        if skip_versions
        else reconcile_versions(
            list(ds.recordings), tuple(dcfg["reconciliation_versions"]), offset, thr, max_iv
        )
    )
    noted = list(dcfg["version_notes"][dcfg["canonical_version"]]["changed_recordings"])
    if not all(isinstance(k, str) for k in noted):
        raise TypeError(f"version_notes.changed_recordings must be quoted strings, got {noted!r}")
    reference = load_yaml(CONFIG_DIR / "reference" / "blueprint_audit.yaml")
    recon = (
        reconcile(reference, results["blueprint_definitions"], versions, noted)
        if versions is not None
        else None
    )
    deterministic = {
        "results": results,
        "version_reconciliation": versions,
        "blueprint_reconciliation": recon,
    }
    results_sha = sha256_json(deterministic)

    provenance = {
        "run_started_utc": started,
        "git": git_state(),
        "config_sha256": config_hash(cfg),
        "dataset_config_sha256": config_hash(dcfg),
        "manifest_files_sha256": ds.manifest_files_sha256,
        "archive": {
            k: record.get(k) for k in ("version", "version_doi", "md5", "sha256", "retrieved_utc")
        },
        "environment": environment(),
        "access_scope": ds.scope.value,
    }
    run_id = make_run_id("ALL-AGG-audit-structural")
    out_dir = REPO_ROOT / "experiments" / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "run_id": run_id,
        "results_sha256": results_sha,
        "provenance": provenance,
        **deterministic,
    }
    jpath = out_dir / "audit_structural.json"
    jpath.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "audit_structural.md").write_text(render_markdown(report), encoding="utf-8")

    d, ts, cg = results["dataset"], results["timestamps"], results["cgm"]
    g0 = evaluate_g0(
        archive_record=record,
        pinned=dcfg["versions"][dcfg["canonical_version"]],
        canonical_version=int(dcfg["canonical_version"]),
        archive_verified=archive_ok,
        manifest_verified=manifest_ok,
        measured={
            "recording_files": d["recording_files"],
            "recordings": d["recordings"],
            "patients": d["patients"],
            "rows": d["rows"],
            "cgm_readings": d["cgm_readings"],
            "rows_without_cgm_by_recording": d["rows_without_cgm_by_recording"],
            "summary_present": results["identity"]["summary"]["present"],
            "manifest_files_sha256": ds.manifest_files_sha256,
        },
        expected=cfg["gates"]["g0"],
        published_cgm=int(cfg["gates"]["g0"]["published_cgm_readings"]),
        noted_recordings=noted,
        reconciliation=recon,
    )
    iss = results["issues"]
    g1 = evaluate_g1(
        measured={
            "cgm_parse_rate": cg["parse_rate"],
            "cgm_parsed": cg["parsed_with_valid_timestamp"],
            "cgm_cells_nonempty": cg["cells_nonempty"],
            "interval_le_max_rate": ts["interval_le_max_rate"],
            "cgm_intervals": ts["cgm_intervals"],
            "timestamp_parse_rate": ts["timestamp_parse_rate"],
            "duplicates": {k: v for k, v in iss.items() if "duplicate" in k},
            "invalid_cgm": {
                "unparseable": sum(
                    v
                    for k, v in iss.items()
                    if k.endswith("value_unparseable") and k.startswith("error")
                ),
                "out_of_range": cg["out_of_plausible_range"],
            },
            "issues": iss,
        },
        criteria=cfg["gates"]["g1"],
    )
    rel = jpath.relative_to(REPO_ROOT).as_posix()
    evidence = {
        "audit_report": rel,
        "manifest": dcfg["paths"]["manifest_json"],
        "archive_provenance": archive_path(spec, dcfg)
        .with_suffix(".provenance.json")
        .relative_to(REPO_ROOT)
        .as_posix(),
    }
    gate_prov = {**provenance, "audit_run_id": run_id, "audit_results_sha256": results_sha}
    now = utc_now_iso()
    write_gate(g0, gate_prov, evidence, now)
    write_gate(g1, gate_prov, evidence, now)
    return {
        "run_id": run_id,
        "report": rel,
        "results_sha256": results_sha,
        "G0": g0["status"],
        "G1": g1["status"],
        "reconciliation": None if recon is None else {r["metric"]: r["status"] for r in recon},
    }


def render_markdown(report: dict[str, Any]) -> str:
    r = report["results"]
    d, t, c, m = r["dataset"], r["timestamps"], r["cgm"], r["medication"]
    lines = [
        f"# Structural audit — {report['run_id']}",
        "",
        f"- results_sha256: `{report['results_sha256']}`",
        f"- git: `{report['provenance']['git']['commit']}` (dirty: {report['provenance']['git']['dirty']})",
        f"- manifest files_sha256: `{report['provenance']['manifest_files_sha256']}`",
        f"- archive: figshare v{report['provenance']['archive']['version']} "
        f"sha256 `{report['provenance']['archive']['sha256']}`",
        f"- access scope: {report['provenance']['access_scope']} (aggregate-only)",
        "",
        "## Dataset",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Recording files / recordings / patients | {d['recording_files']} / {d['recordings']} / {d['patients']} |",
        f"| Recordings per patient | {d['recordings_per_patient']} |",
        f"| Rows / rows without CGM | {d['rows']} / {d['rows_without_cgm']} {d['rows_without_cgm_by_recording']} |",
        f"| CGM readings | {d['cgm_readings']} |",
        f"| Monitored (patient-)days | {d['monitored_days']} |",
        f"| Recording days min/median/max | {d['recording_days_min_median_max']} |",
        "",
        "## Timestamps and CGM",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Timestamp parse rate | {t['timestamp_parse_rate']} |",
        f"| Intervals (n) / ≤20 min share / exactly-15 share | {t['cgm_intervals']} / {t['interval_le_max_rate']} / {t['interval_exactly_15_rate']} |",
        f"| Interval histogram (min) | {t['interval_histogram_min']} |",
        f"| Gaps >30 / >60 min; max gap | {t['gaps_gt_30_min']} / {t['gaps_gt_60_min']}; {t['max_gap_min']} min |",
        f"| CGM parse rate | {c['parse_rate']} |",
        f"| CGM min/p1/median/p99/max | {c['min_p1_median_p99_max']} |",
        f"| ≤40 mg/dL (floor) / out of [20,600] | {c['at_or_below_floor']} / {c['out_of_plausible_range']} |",
        f"| Values on the 1.8 mg/dL grid (0.1 mmol/L origin) | {c['fraction_multiple_of_1_8']} |",
        f"| Quality flags | {c['quality_flags']} |",
        "",
        "## Medication and meals (structural)",
        "",
        f"- columns: {m['columns']}",
        f"- entries with amount+unit: {m['entries_with_amount_unit_rate']}",
        f"- vocabulary sizes: {m['vocabulary_size']}",
        f"- administration alignment: {m['administration_alignment']}",
        f"- meals: {r['meals']}",
        "",
        "## Issues",
        "",
        f"{r['issues']}",
        "",
    ]
    if report.get("blueprint_reconciliation"):
        lines += [
            "## Blueprint reconciliation",
            "",
            "| Metric | Blueprint | Measured (v5) | Status |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {x['metric']} | {x['blueprint_value']} | {x['measured_v5']} | {x['status']} |"
            for x in report["blueprint_reconciliation"]
        ]
    return "\n".join(lines) + "\n"


__all__ = ["Path", "render_markdown", "run_audit", "thresholds_from_config"]
