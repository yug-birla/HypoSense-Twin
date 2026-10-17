"""`hyposense audit events`: label build + event audit on figshare v5 (canonical) and v2/v1
(legacy reproduction), blueprint reconciliation, Gates G2 and G3b, with full provenance.

Outputs:
- experiments/runs/<run_id>/audit_events.json   (provenance + deterministic results)
- experiments/runs/<run_id>/audit_events.md
- artifacts/gates/G2.json, artifacts/gates/G3b.json

`results_sha256` hashes only the deterministic content: the same data, code and config give
the same value.
"""

from __future__ import annotations

import json
from typing import Any

from hyposense.audit.events import measure_events
from hyposense.audit.gates import evaluate_g2, evaluate_g3b, write_gate
from hyposense.audit.reconcile import equal_values, reconcile
from hyposense.audit.versions import load_version, per_file_counts
from hyposense.common.config import CONFIG_DIR, REPO_ROOT, config_hash, load_config, load_yaml
from hyposense.common.hashing import sha256_json
from hyposense.common.provenance import environment, git_state, make_run_id, utc_now_iso
from hyposense.common.timeconv import parse_utc_offset
from hyposense.data.dataset import AccessScope, load_dataset
from hyposense.data.partition import load_partition
from hyposense.data.source import dataset_config
from hyposense.labels.config import LabelConfig

PROVISIONAL = [
    "Treated status uses the blueprint audit's (legacy) definition until the S3 medication "
    "parser exists; G2 is re-evaluated in S3.",
]


def run_event_audit(*, skip_versions: bool = False) -> dict[str, Any]:
    cfg, dcfg = load_config(), dataset_config()
    started = utc_now_iso()
    lc = LabelConfig.from_config(cfg)
    offset = str(cfg["time"]["assumed_utc_offset"])
    offset_s = parse_utc_offset(offset)
    part = load_partition()
    g3b_cfg = cfg["gates"]["g3b"]

    ds = load_dataset(AccessScope.AGGREGATE_AUDIT)
    canonical = measure_events(ds.recordings, lc, offset_s, part, g3b_cfg)

    versions: dict[str, Any] | None = None
    recon = None
    if not skip_versions:
        base = per_file_counts(list(ds.recordings))
        versions = {}
        reference = load_yaml(CONFIG_DIR / "reference" / "blueprint_events.yaml")
        for v in dcfg["reconciliation_versions"]:
            recs, _ = load_version(int(v), offset)
            counts = per_file_counts(recs)
            versions[f"v{v}"] = {
                "blueprint_definitions": measure_events(recs, lc, offset_s, part, g3b_cfg)[
                    "blueprint_definitions"
                ],
                "files_differing_from_canonical": {
                    k: True for k in sorted(set(base) & set(counts)) if base[k] != counts[k]
                },
                "only_in_canonical": sorted(set(base) - set(counts)),
                "only_in_this_version": sorted(set(counts) - set(base)),
            }
        noted = list(dcfg["version_notes"][dcfg["canonical_version"]]["changed_recordings"])
        recon = reconcile(reference, canonical["blueprint_definitions"], versions, noted)
        versions["exact_reproduction_counts"] = {
            v: exact_matches(d["blueprint_definitions"], reference["values"])
            for v, d in list(versions.items())
        }

    deterministic = {
        "results": canonical,
        "version_reproduction": versions,
        "blueprint_reconciliation": recon,
    }
    results_sha = sha256_json(deterministic)
    provenance = {
        "run_started_utc": started,
        "git": git_state(),
        "config_sha256": config_hash(cfg),
        "label_config_sha256": lc.sha256,
        "dataset_config_sha256": config_hash(dcfg),
        "manifest_files_sha256": ds.manifest_files_sha256,
        "partition_sha256": cfg["partition"]["sha256"],
        "environment": environment(),
        "access_scope": ds.scope.value,
    }
    run_id = make_run_id("ALL-AGG-audit-events")
    out_dir = REPO_ROOT / "experiments" / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "run_id": run_id,
        "results_sha256": results_sha,
        "provenance": provenance,
        **deterministic,
    }
    jpath = out_dir / "audit_events.json"
    jpath.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    (out_dir / "audit_events.md").write_text(render_markdown(report), encoding="utf-8")

    bp = canonical["by_partition"]["E"]
    g2 = evaluate_g2(
        measured={
            "E_treated_L1": bp["treated_L1"],
            "E_treated_with_L1": bp["treated_with_L1"],
            "E_treated_m_w": bp["treated_m_w"],
            "E_all": {"L1": bp["L1"], "patients_with_L1": bp["patients_with_L1"]},
        },
        criteria=cfg["gates"]["g2"],
        provisional_reasons=PROVISIONAL,
    )
    g3b = evaluate_g3b(
        measured={
            **canonical["label_validity"],
            "sensor_floor_run": canonical["L1_annotations"].get("sensor_floor_run", 0),
        },
        criteria=g3b_cfg,
    )
    evidence = {
        "event_audit": jpath.relative_to(REPO_ROOT).as_posix(),
        "label_config_sha256": lc.sha256,
    }
    gate_prov = {**provenance, "audit_run_id": run_id, "audit_results_sha256": results_sha}
    now = utc_now_iso()
    write_gate(g2, gate_prov, evidence, now)
    write_gate(g3b, gate_prov, evidence, now)
    return {
        "run_id": run_id,
        "report": jpath.relative_to(REPO_ROOT).as_posix(),
        "results_sha256": results_sha,
        "G2": g2["status"],
        "G3b": g3b["status"],
        "legacy_exact_reproduction": None
        if versions is None
        else versions["exact_reproduction_counts"],
        "reconciliation_status_counts": None
        if recon is None
        else {
            s: sum(1 for r in recon if r["status"] == s)
            for s in sorted({r["status"] for r in recon})
        },
    }


def exact_matches(measured: dict[str, Any], reference: dict[str, Any]) -> str:
    n = sum(1 for k, ref in reference.items() if equal_values(measured.get(k), ref["value"]))
    return f"{n}/{len(reference)}"


def render_markdown(report: dict[str, Any]) -> str:
    r = report["results"]
    pt, lv = r["prediction_times"], r["label_validity"]
    lines = [
        f"# Event audit — {report['run_id']}",
        "",
        f"- results_sha256: `{report['results_sha256']}`",
        f"- git: `{report['provenance']['git']['commit']}` (dirty: {report['provenance']['git']['dirty']})",
        f"- label_config_sha256: `{report['provenance']['label_config_sha256']}`",
        f"- manifest files_sha256: `{report['provenance']['manifest_files_sha256']}`",
        f"- access scope: {report['provenance']['access_scope']} (aggregate-only)",
        "",
        "## Episodes (figshare v5)",
        "",
        "| Level | Episodes | Patients with | Per affected patient q1/med/q3/max | Top-5 share | Duration q1/med/q3 (min) | End reasons |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, key in (("L1", "L1"), ("L2", "L2"), ("L1 single-reading", "L1_single")):
        d = r["episodes"][key]
        lines.append(
            f"| {name} | {d['episodes']} | {d['patients_with']} | "
            f"{d['per_affected_patient_q1_median_q3_max']} | {d['top5_share']} | "
            f"{d['duration_min_q1_median_q3']} | {d['end_reasons']} |"
        )
    lines += [
        "",
        "## Prediction times",
        "",
        f"- readings {pt['readings']}; eligible {pt['eligible']} ({pt['eligible_share_of_readings']}); positive {pt['positive']} (prevalence {pt['prevalence']})",
        f"- ineligibility reasons: {pt['ineligibility_reasons']}",
        f"- per-recording eligible share min/median/max: {pt['per_recording_eligible_share_min_median_max']}",
        f"- warnable L1 episodes: {r['L1_warnable']}",
        "",
        "## Partitions (aggregate)",
        "",
        json.dumps(r["by_partition"]),
        "",
        "## Label validity",
        "",
        json.dumps(lv),
        "",
        "## Annotations and sensor-floor runs",
        "",
        f"- L1 annotations: {r['L1_annotations']}",
        f"- sensor-floor runs: {r['sensor_floor_runs']}",
        "",
    ]
    if report.get("blueprint_reconciliation"):
        vr = report["version_reproduction"]["exact_reproduction_counts"]
        lines += [
            f"## Legacy reproduction: exact matches {vr}",
            "",
            "| Metric | Blueprint | Measured (v5) | Status |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {x['metric']} | {x['blueprint_value']} | {x['measured_v5']} | {x['status']} |"
            for x in report["blueprint_reconciliation"]
        ]
    return "\n".join(lines) + "\n"
