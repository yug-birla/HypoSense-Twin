"""Protocol freeze (IMPLEMENTATION_PLAN "FREEZE"; ARCHITECTURE §6; ANALYSIS_PLAN §4-6).

`hyposense freeze --check` evaluates every freeze invariant and reports. `hyposense freeze` writes
`artifacts/freeze/FREEZE.json` only if EVERY invariant passes. It FAILS CLOSED: any failure is
"ERROR — FREEZE ABORTED". There is no warning-and-continue path.

Invariants:
- clean working tree (strict: nothing modified or untracked outside ignored files);
- ANALYSIS_PLAN §5 and §6 FINAL; no Class C proposal AWAITING approval/decision;
- pharmacist review recorded in configs/pharma.yaml (`reviewed_by`), unless the owner recorded an
  explicit waiver (`pharmacist_waiver`) — Blueprint §12.3; no ILLUSTRATIVE kernel parameter;
- data manifest verified; partition verified (pinned hash, provenance, patient set);
- no run artefact records partition E (sealed partition never used);
- freeze candidate: two candidate runs on one clean commit with identical results_sha256 and
  identical artefact file hashes; no change to code, configs or lock files since that commit;
  the candidate artefact loads (fail-closed compatibility checks) with the canonical calibrator;
- the full Python test suite passes (run by this command).

This module never loads E and never enables `AccessScope.ALL_AFTER_FREEZE`; the confirmatory run
(S9) verifies FREEZE.json before any E access.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from hyposense.common.config import REPO_ROOT, config_hash, load_config
from hyposense.common.hashing import sha256_file, sha256_json
from hyposense.common.provenance import _git, utc_now_iso

FREEZE_DIR = REPO_ROOT / "artifacts" / "freeze"
FREEZE_JSON = FREEZE_DIR / "FREEZE.json"
PLAN = REPO_ROOT / "docs" / "protocol" / "ANALYSIS_PLAN.md"
PROPOSALS = REPO_ROOT / "docs" / "PROPOSALS.md"
CODE_PATHS = (
    "src",
    "configs",
    "uv.lock",
    "pyproject.toml",
    "frontend/package-lock.json",
    "frontend/src",
)
# implemented at S9; it must verify this record before any E access
CONFIRMATORY_COMMAND = "uv run hyposense confirm --freeze artifacts/freeze/FREEZE.json"


class FreezeAborted(RuntimeError):
    """ERROR — FREEZE ABORTED."""


def _check(results: list[dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    results.append({"check": name, "status": "PASS" if ok else "ERROR", "detail": detail})


def plan_is_final(text: str) -> tuple[bool, str]:
    def section(title: str) -> str:
        i = text.find(title)
        if i < 0:
            return ""
        j = text.find("\n## ", i + len(title))
        return text[i : j if j >= 0 else len(text)]

    s5 = section("## 5. Primary analysis")
    s6 = section("## 6. Interpretation matrix")
    problems = []
    for name, sec in (("§5", s5), ("§6", s6)):
        if "Status: **FINAL" not in sec:
            problems.append(f"{name} not FINAL")
        if "DRAFT" in sec or "PENDING (S5)" in sec:
            problems.append(f"{name} contains DRAFT/PENDING text")
    return not problems, "; ".join(problems) or "§5 and §6 FINAL"


def open_class_c(text: str) -> list[str]:
    """Proposals whose status line is still awaiting approval or decision."""
    out, current = [], None
    for line in text.splitlines():
        if line.startswith("### "):
            current = line[4:].split("·")[0].strip()
        elif (
            line.startswith("**Status:")
            and current
            and current.startswith("P-C")
            and "AWAITING" in line
        ):
            out.append(current)
    return out


def pharmacist_status(pharma: dict[str, Any]) -> tuple[bool, str]:
    if pharma.get("reviewed_by"):
        return True, f"reviewed_by: {pharma['reviewed_by']}"
    waiver = pharma.get("pharmacist_waiver")
    if waiver:
        return True, f"owner waiver recorded: {waiver}"
    return False, "PHARMACIST REVIEW PENDING (configs/pharma.yaml reviewed_by is null; no waiver)"


def e_partition_runs(runs_dir: Path) -> list[str]:
    bad = []
    for f in sorted(runs_dir.glob("*/results.json")):
        try:
            doc = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            bad.append(f"{f.parent.name} (unreadable: cannot prove it is not E)")
            continue
        part = doc.get("results", {}).get("partition", doc.get("partition"))
        if part == "E" or f.parent.name.startswith("E-"):
            bad.append(f.parent.name)
    return bad


def candidate_runs(runs_dir: Path) -> list[dict[str, Any]]:
    out = []
    for f in sorted(runs_dir.glob("T-AGG-candidate-*/results.json")):
        out.append(json.loads(f.read_text("utf-8")))
    return out


def evaluate(run_tests: bool = True) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """All freeze invariants. Returns (checks, facts for FREEZE.json)."""
    checks: list[dict[str, Any]] = []
    facts: dict[str, Any] = {}
    cfg, pharma = load_config(), load_config("pharma.yaml")

    status = _git("status", "--porcelain", "--untracked-files=all")
    _check(
        checks,
        "clean_working_tree",
        status == "",
        "git status --porcelain is empty"
        if status == ""
        else f"dirty: {(status or 'git unavailable').splitlines()[:5]}",
    )
    head = (_git("rev-parse", "HEAD") or "").strip()
    facts["source_commit"] = head

    ok, detail = plan_is_final(PLAN.read_text("utf-8"))
    _check(checks, "analysis_plan_final", ok, detail)
    pending = open_class_c(PROPOSALS.read_text("utf-8"))
    _check(
        checks,
        "class_c_resolved",
        not pending,
        "no Class C proposal awaiting" if not pending else f"awaiting: {pending}",
    )

    ok, detail = pharmacist_status(pharma)
    _check(checks, "pharmacist_review", ok, detail)
    illustrative = [
        f"{g}.{k}.{p}"
        for g in ("insulin", "secretagogue")
        for k, spec in pharma.get(g, {}).items()
        for p, v in spec.items()
        if isinstance(v, dict) and v.get("status") == "ILLUSTRATIVE"
    ]
    _check(
        checks,
        "no_illustrative_kernels",
        not illustrative,
        "none" if not illustrative else f"ILLUSTRATIVE: {illustrative}",
    )

    try:
        from hyposense.data.dataset import extracted_root
        from hyposense.data.manifest import read_manifest, verify_manifest
        from hyposense.data.source import dataset_config

        dcfg = dataset_config()
        man_path = REPO_ROOT / dcfg["paths"]["manifest_json"]
        verify_manifest(extracted_root(), read_manifest(man_path))
        facts["data_manifest_sha256"] = sha256_file(man_path)
        _check(checks, "data_manifest", True, "files match data/MANIFEST")
    except Exception as exc:  # any failure aborts
        _check(checks, "data_manifest", False, f"{type(exc).__name__}: {exc}")
    try:
        from hyposense.audit.partition_check import verify_partition
        from hyposense.data.partition import partition_path

        pv = verify_partition()
        facts["partition_sha256"] = sha256_file(partition_path(cfg))
        _check(checks, "partition", pv["status"] == "PASS", json.dumps(pv["checks"]))
    except Exception as exc:
        _check(checks, "partition", False, f"{type(exc).__name__}: {exc}")

    bad = e_partition_runs(REPO_ROOT / "experiments" / "runs")
    _check(
        checks, "e_sealed", not bad, "no run records partition E" if not bad else f"E runs: {bad}"
    )

    runs = candidate_runs(REPO_ROOT / "experiments" / "runs")
    cand_ok, cand_detail = False, "fewer than two candidate runs"
    if len(runs) >= 2:
        a, b = runs[-2], runs[-1]
        ca, cb = a["provenance"]["git"], b["provenance"]["git"]
        same = (
            ca["commit"] == cb["commit"]
            and ca["dirty"] is False
            and cb["dirty"] is False
            and a["results_sha256"] == b["results_sha256"]
            and a["results"]["artifact"]["files"] == b["results"]["artifact"]["files"]
        )
        changed = _git("diff", "--name-only", ca["commit"], "HEAD", "--", *CODE_PATHS)
        cand_ok = same and changed == ""
        cand_detail = (
            f"runs {a['run_id']} / {b['run_id']} on {ca['commit'][:7]}: identical={same}; "
            f"code/config changed since: {changed!r}"
        )
        facts["candidate"] = {
            "runs": [a["run_id"], b["run_id"]],
            "commit": ca["commit"],
            "results_sha256": a["results_sha256"],
            **a["results"]["artifact"],
            "artifact_directory": a["provenance"].get("artifact_directory"),
            "canonical": a["results"]["canonical"],
        }
    _check(checks, "candidate_reproducible", cand_ok, cand_detail)
    if cand_ok:
        try:
            from hyposense.models.artifact import load_artifact

            d = REPO_ROOT / facts["candidate"]["artifact_directory"]
            m = load_artifact(d, cfg, pharma)
            facts["candidate"]["manifest_sha256"] = m.manifest_sha256
            same_files = m.manifest["files"] == facts["candidate"]["files"]
            tracked = _git(
                "ls-files", "--error-unmatch", str(d.relative_to(REPO_ROOT) / "model.txt")
            )
            ok = (
                m.calibrator.method == cfg["calibration"]["method"]
                and same_files
                and tracked is not None
            )
            _check(
                checks,
                "candidate_artifact_loads",
                ok,
                f"{m.model_version} ({m.calibrator.method}); files match run record: "
                f"{same_files}; committed: {tracked is not None}",
            )
        except Exception as exc:
            _check(checks, "candidate_artifact_loads", False, f"{type(exc).__name__}: {exc}")
    else:
        _check(checks, "candidate_artifact_loads", False, "no reproducible candidate")

    if run_tests:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        tail = proc.stdout.strip().splitlines()[-1:] if proc.stdout else []
        _check(checks, "python_test_suite", proc.returncode == 0, " ".join(tail))
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        try:
            fe = subprocess.run(
                [npm, "test"], cwd=REPO_ROOT / "frontend", capture_output=True, text=True
            )
            fe_ok, fe_tail = fe.returncode == 0, (fe.stdout.strip().splitlines() or [""])[-1]
        except OSError as exc:
            fe_ok, fe_tail = False, f"npm unavailable: {exc}"
        _check(checks, "frontend_test_suite", fe_ok, fe_tail)
        facts["tests"] = {
            "python": {"returncode": proc.returncode, "summary": " ".join(tail)},
            "frontend": {"ok": fe_ok, "summary": fe_tail},
        }
    else:
        _check(checks, "python_test_suite", False, "not run (--check without --tests)")

    from hyposense.features.spec import spec_sha256
    from hyposense.medication.dictionary import DICTIONARY_PATH

    facts.update(
        config_sha256=config_hash(cfg),
        pharma_sha256=sha256_json(pharma),
        dictionary_sha256=sha256_file(DICTIONARY_PATH),
        feature_spec_sha256=spec_sha256(cfg["features"]),
        analysis_plan_sha256=sha256_file(PLAN),
        uv_lock_sha256=sha256_file(REPO_ROOT / "uv.lock"),
        npm_lock_sha256=sha256_file(REPO_ROOT / "frontend" / "package-lock.json"),
        code_tree={p: (_git("rev-parse", f"HEAD:{p}") or "").strip() for p in CODE_PATHS},
        label_config={"event": cfg["event"], "eligibility": cfg["eligibility"]},
        policy_config=cfg["policy"],
        calibration_config=cfg["calibration"],
        seeds={
            "model": cfg["model"]["seed"],
            "cv": cfg["cv"]["seed"],
            "bootstrap": cfg["bootstrap"]["seed"],
            "sa7_fold_seeds": cfg["sensitivity"]["fold_seeds_sa7"],
        },
        pharmacist=pharmacist_status(pharma)[1],
    )
    return checks, facts


def freeze(write: bool, run_tests: bool = True) -> dict[str, Any]:
    checks, facts = evaluate(run_tests=run_tests)
    errors = [c for c in checks if c["status"] != "PASS"]
    report = {"checks": checks, "errors": len(errors)}
    if errors:
        report["result"] = "ERROR — FREEZE ABORTED"
        return report
    if not write:
        report["result"] = "ALL CHECKS PASS (no record written: --check)"
        return report
    if FREEZE_JSON.exists():
        report["result"] = (
            "ERROR — FREEZE ABORTED: a freeze record already exists (never overwritten)"
        )
        report["errors"] = 1
        return report
    record = {
        "freeze_id": f"protocol-freeze-v1-{utc_now_iso()}",
        "created_utc": utc_now_iso(),
        **facts,
        "confirmatory_command": CONFIRMATORY_COMMAND,
        "checks": checks,
    }
    record["record_sha256"] = sha256_json(record)
    FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    FREEZE_JSON.write_text(json.dumps(record, indent=1, default=str) + "\n", "utf-8", newline="\n")
    report["result"] = f"FROZEN: {FREEZE_JSON.relative_to(REPO_ROOT).as_posix()}"
    report["record_sha256"] = record["record_sha256"]
    return report
