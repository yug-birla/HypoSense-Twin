"""`hyposense audit medication`: S3 medication audit, G3, G2 re-check with the production
treated definition, representation QA (TUNING only). Full provenance.

Outputs:
- experiments/runs/<run_id>/audit_medication.json, audit_medication.md, medication_inventory.json
- artifacts/population/treated_patients.csv (sha256 recorded in the report)
- artifacts/gates/G3.json, artifacts/gates/G2.json (re-evaluated)
"""

from __future__ import annotations

import csv
import json
from typing import Any

from hyposense.audit.events import measure_events
from hyposense.audit.gates import evaluate_g2, evaluate_g3, write_gate
from hyposense.audit.legacy import legacy_treatment
from hyposense.audit.medication import (
    inventory,
    measure_medication,
    parse_all,
    production_treated,
    representation_qa,
)
from hyposense.common.config import REPO_ROOT, config_hash, load_config
from hyposense.common.hashing import sha256_file, sha256_json
from hyposense.common.provenance import environment, git_state, make_run_id, utc_now_iso
from hyposense.common.timeconv import parse_utc_offset
from hyposense.data.dataset import AccessScope, load_dataset
from hyposense.data.partition import load_partition
from hyposense.labels.config import LabelConfig
from hyposense.medication.dictionary import load_dictionary
from hyposense.medication.exposure import load_kernel_set
from hyposense.medication.recording import TreatmentStatus

TREATED_PATH = REPO_ROOT / "artifacts" / "population" / "treated_patients.csv"


def write_treated(status: dict[str, TreatmentStatus], partition: dict[str, str]) -> str:
    TREATED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TREATED_PATH.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["patient_id", "partition", "treated", "insulin", "sulfonylurea", "glinide"])
        for p, s in sorted(status.items()):
            w.writerow(
                [
                    p,
                    partition.get(p, ""),
                    int(s.treated),
                    int(s.insulin),
                    int(s.sulfonylurea),
                    int(s.glinide),
                ]
            )
    return sha256_file(TREATED_PATH)


def run_medication_audit() -> dict[str, Any]:
    cfg, pharma = load_config(), load_config("pharma.yaml")
    started = utc_now_iso()
    d = load_dictionary()
    ks = load_kernel_set(pharma, float(cfg["exposure"]["timing_unknown_after_h"]))
    rules = pharma["formulation_rules"]
    part = load_partition()
    lc = LabelConfig.from_config(cfg)

    ds = load_dataset(AccessScope.AGGREGATE_AUDIT)
    meds = parse_all(ds.recordings, d, rules)
    legacy: dict[str, bool] = {}
    for r in ds.recordings:
        t = legacy_treatment(r)
        pid = r.identity.patient_id
        legacy[pid] = legacy.get(pid, False) or t.insulin_any or t.secretagogue_any
    status = production_treated(ds.recordings, meds)
    results = measure_medication(ds.recordings, ds.summary, meds, part, d, ks, legacy)
    inv = inventory(ds.recordings, meds, part)
    treated_sha = write_treated(status, part)

    # G2 re-check with the production treated definition
    offset_s = parse_utc_offset(str(cfg["time"]["assumed_utc_offset"]))
    events = measure_events(
        ds.recordings,
        lc,
        offset_s,
        part,
        cfg["gates"]["g3b"],
        treated_override={p: s.treated for p, s in status.items()},
    )
    bp = events["by_partition"]["E"]
    g2 = evaluate_g2(
        measured={
            "E_treated_L1": bp["treated_L1"],
            "E_treated_with_L1": bp["treated_with_L1"],
            "E_treated_m_w": bp["treated_m_w"],
            "E_all": {"L1": bp["L1"], "patients_with_L1": bp["patients_with_L1"]},
        },
        criteria=cfg["gates"]["g2"],
        provisional_reasons=[
            "Treated status from the production medication parser (S3); "
            "supersedes the provisional legacy-definition evaluation (S2)."
        ],
    )
    g2["comparison_with_s2_provisional"] = {
        "E_treated_L1": [154, bp["treated_L1"]],
        "E_treated_with_L1": [30, bp["treated_with_L1"]],
        "E_treated_m_w": [9.23, bp["treated_m_w"]],
        "E_treated_patients": [51, bp["treated_patients"]],
    }
    g3 = evaluate_g3(measured=results["g3_inputs"], criteria=cfg["gates"]["g3"])

    # representation QA on TUNING data only (P-C5)
    tds = load_dataset(AccessScope.TUNING_ONLY)
    qa = representation_qa(tds.recordings, tds.summary, d, rules, ks, lc)

    deterministic: dict[str, Any] = {
        "results": results,
        "g2_recheck_partition_E": bp,
        "strata_production": events["strata_counts"],
        "treated_patients_sha256": treated_sha,
        "representation_qa_T": qa,
        "dictionary_sha256": d.sha256,
        "pharma_sha256": config_hash(pharma),
    }
    hashed = dict(deterministic)
    hashed["representation_qa_T"] = {
        k: v for k, v in qa.items() if k != "seconds_per_1000_readings"
    }  # wall-clock excluded
    results_sha = sha256_json(hashed)
    provenance = {
        "run_started_utc": started,
        "git": git_state(),
        "config_sha256": config_hash(cfg),
        "pharma_sha256": config_hash(pharma),
        "dictionary_sha256": d.sha256,
        "label_config_sha256": lc.sha256,
        "manifest_files_sha256": ds.manifest_files_sha256,
        "partition_sha256": cfg["partition"]["sha256"],
        "environment": environment(),
        "access_scope": f"{ds.scope.value} (+ {tds.scope.value} for representation QA)",
    }
    run_id = make_run_id("ALL-AGG-audit-medication")
    out = REPO_ROOT / "experiments" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "run_id": run_id,
        "results_sha256": results_sha,
        "provenance": provenance,
        **deterministic,
    }
    jpath = out / "audit_medication.json"
    jpath.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    (out / "medication_inventory.json").write_text(
        json.dumps(inv, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    (out / "audit_medication.md").write_text(render_markdown(report, g2, g3), encoding="utf-8")
    evidence = {
        "medication_audit": jpath.relative_to(REPO_ROOT).as_posix(),
        "treated_patients": TREATED_PATH.relative_to(REPO_ROOT).as_posix(),
    }
    gate_prov = {**provenance, "audit_run_id": run_id, "audit_results_sha256": results_sha}
    now = utc_now_iso()
    write_gate(g3, gate_prov, evidence, now)
    write_gate(g2, gate_prov, evidence, now)
    return {
        "run_id": run_id,
        "results_sha256": results_sha,
        "G3": g3["status"],
        "G2": g2["status"],
        "treated": results["treated"]["by_partition"]["ALL"]["treated"],
        "treated_patients_sha256": treated_sha,
        "g2_comparison": g2["comparison_with_s2_provisional"],
        "g3_measured": {c["id"]: c["measured"] for c in g3["checks"]},
    }


def render_markdown(report: dict[str, Any], g2: dict[str, Any], g3: dict[str, Any]) -> str:
    r = report["results"]
    qa = report["representation_qa_T"]
    prov = report["provenance"]
    lines = [
        f"# Medication audit — {report['run_id']}",
        "",
        f"- results_sha256: `{report['results_sha256']}`",
        f"- git: `{prov['git']['commit']}` (dirty: {prov['git']['dirty']})",
        f"- dictionary sha256 `{report['dictionary_sha256']}`; pharma `{report['pharma_sha256']}`",
        f"- treated_patients.csv sha256 `{report['treated_patients_sha256']}`",
        "",
        "## Coverage",
        "",
        f"- entries: {json.dumps(r['entries'])}",
        f"- rates: {json.dumps(r['rates'])}",
        "",
        "## Treated population",
        "",
        json.dumps(r["treated"]),
        "",
        "## Day coverage / CSII / i.v.",
        "",
        f"- day coverage: {json.dumps(r['day_coverage_treated_recordings'])}",
        f"- CSII: {json.dumps(r['csii'])}",
        f"- i.v. column: {json.dumps(r['iv_column'])}",
        f"- i.v. glucose: {json.dumps(r['iv_glucose'])}",
        "",
        f"## G3: {g3['status']}",
        "",
    ]
    lines += [f"- {c['id']}: {c['status']} ({c['measured']})" for c in g3["checks"]]
    lines += [
        "",
        f"## G2 re-check: {g2['status']}",
        "",
        f"- {json.dumps(g2['comparison_with_s2_provisional'])}",
        "",
        "## Representation QA (TUNING only)",
        "",
        "```",
        json.dumps(qa, indent=1),
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"
