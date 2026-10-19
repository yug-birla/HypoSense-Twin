"""`hyposense` command-line interface (cross-platform replacement for Makefile targets, ADR-006).

hyposense data fetch [--version N]      download + verify the pinned figshare archive
hyposense data extract [--overwrite]    extract allow-listed T2DM files from the canonical archive
hyposense data manifest [--write]       verify (default) or create data/MANIFEST.json
hyposense data validate                 manifest check + load every recording; issue summary
hyposense partition verify              pinned hash, patient-set agreement, counts
hyposense audit run                     structural audit + version reconciliation + G0/G1
hyposense audit events                  labels, event audit, legacy reproduction, G2/G3b
hyposense audit medication              medication audit, G3, G2 re-check (production treated)
hyposense audit features [--workers N]  S4 feature audit on T: truncation equality at every
                                        eligible time, replay parity, perturbation, distributions
hyposense features spec                 write artifacts/features/feature_spec.json (registry)
hyposense eval m0 [--resamples N]       S5: Table A.2 reproduction + M0 on v5 T (DEVELOPMENT)
hyposense eval registry                 write artifacts/evaluation/metric_registry.json
hyposense dev s6 [--workers N]          S6 development workflow on T (tuning, ladder, experiments)
hyposense dev artifact [--level M3]      S7 DEVELOPMENT model artefact (T only)
hyposense dev s7 [--model DIR]           S7 engineering evidence (parity, determinism, latency)
hyposense serve [--model DIR] [--port N] replay API (refuses to start on an artefact mismatch)
hyposense dev candidate                  freeze-candidate workflow on T (run twice)
hyposense freeze [--check]               protocol freeze; fails closed (ERROR — FREEZE ABORTED)
hyposense gates show                  print the latest gate results
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from hyposense import __version__


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_data_fetch(args: argparse.Namespace) -> int:
    from hyposense.data.source import fetch_archive

    _print(fetch_archive(args.version, force=args.force))
    return 0


def cmd_data_extract(args: argparse.Namespace) -> int:
    from hyposense.data.source import extract_archive

    written = extract_archive(overwrite=args.overwrite)
    print(f"extracted {len(written)} files")
    return 0


def cmd_data_manifest(args: argparse.Namespace) -> int:
    from hyposense.common.config import REPO_ROOT
    from hyposense.data.dataset import extracted_root
    from hyposense.data.manifest import (
        build_manifest,
        read_manifest,
        verify_manifest,
        write_manifest,
    )
    from hyposense.data.source import archive_path, archive_spec, dataset_config

    dcfg = dataset_config()
    json_path = REPO_ROOT / dcfg["paths"]["manifest_json"]
    sum_path = REPO_ROOT / dcfg["paths"]["manifest_sha256"]
    root = extracted_root()
    if args.write:
        sidecar = archive_path(archive_spec(None, dcfg), dcfg).with_suffix(".provenance.json")
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        manifest = build_manifest(root, record)
        existing = read_manifest(json_path) if json_path.exists() else None
        if existing and existing["files_sha256"] != manifest["files_sha256"] and not args.force:
            print(
                "REFUSED: existing manifest pins different files; use --force only with an "
                "approved data-version change",
                file=sys.stderr,
            )
            return 1
        write_manifest(manifest, json_path, sum_path)
        print(
            f"wrote {json_path.name}: {manifest['n_files']} files, "
            f"files_sha256={manifest['files_sha256']}"
        )
        return 0
    _print(verify_manifest(root, read_manifest(json_path)))
    return 0


def cmd_data_validate(args: argparse.Namespace) -> int:
    from hyposense.data.dataset import AccessScope, load_dataset

    ds = load_dataset(AccessScope.AGGREGATE_AUDIT)
    issues = Counter((i.severity, i.code.value) for r in ds.recordings for i in r.issues)
    _print(
        {
            "scope": ds.scope.value,
            "manifest_files_sha256": ds.manifest_files_sha256,
            "recordings": len(ds.recordings),
            "patients": len({r.identity.patient_id for r in ds.recordings}),
            "summary_rows": len(ds.summary.frame),
            "issues_by_severity_code": {f"{s}:{c}": n for (s, c), n in sorted(issues.items())},
        }
    )
    return 1 if any(s == "error" for s, _ in issues) else 0


def cmd_partition_verify(args: argparse.Namespace) -> int:
    from hyposense.audit.partition_check import verify_partition

    result = verify_partition()
    _print(result)
    return 0 if result["status"] == "PASS" else 1


def cmd_audit_run(args: argparse.Namespace) -> int:
    from hyposense.audit.run import run_audit

    summary = run_audit(skip_versions=args.skip_versions)
    _print(summary)
    return 0 if summary["G1"] != "FAIL" and summary["G0"] != "FAIL" else 1


def cmd_audit_events(args: argparse.Namespace) -> int:
    from hyposense.audit.event_run import run_event_audit

    summary = run_event_audit(skip_versions=args.skip_versions)
    _print(summary)
    return 0 if summary["G2"] != "FAIL" and summary["G3b"] != "FAIL" else 1


def cmd_audit_medication(args: argparse.Namespace) -> int:
    from hyposense.audit.med_run import run_medication_audit

    summary = run_medication_audit()
    _print(summary)
    return 0 if summary["G3"] != "FAIL" and summary["G2"] != "FAIL" else 1


def cmd_audit_features(args: argparse.Namespace) -> int:
    from hyposense.audit.feature_run import run_features_audit

    summary = run_features_audit(workers=args.workers)
    _print(summary)
    ok = (
        summary["truncation"]["mismatches"] == 0
        and summary["parity"]["mismatches"] == 0
        and all(v["mismatches"] == 0 for v in summary["perturbation"].values())
        and summary["tracker_vs_label_builder"]["mismatches"] == 0
        and summary["determinism_two_builds_identical"]
    )
    return 0 if ok else 1


def cmd_features_spec(args: argparse.Namespace) -> int:
    from hyposense.features.export import SPEC_PATH, write_spec

    sha = write_spec()
    print(f"wrote {SPEC_PATH} (sha256 {sha})")
    return 0


def cmd_eval_m0(args: argparse.Namespace) -> int:
    from hyposense.evaluation.m0_run import run_m0

    summary = run_m0(resamples=args.resamples)
    _print(summary)
    return 0 if summary["legacy_reproduction"].get("UNEXPLAINED DIFFERENCE", 0) == 0 else 1


def cmd_eval_registry(args: argparse.Namespace) -> int:
    from hyposense.common.config import REPO_ROOT
    from hyposense.evaluation.registry import registry_document, registry_sha256

    path = REPO_ROOT / "artifacts" / "evaluation" / "metric_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {**registry_document(), "sha256": registry_sha256()}
    path.write_text(
        json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {path} (sha256 {doc['sha256']})")
    return 0


def _latest_model(arg: str | None) -> Path:
    from hyposense.evaluation.s7_artifact import MODELS_DIR, latest_candidate

    if arg:
        return Path(arg)
    found = latest_candidate(MODELS_DIR)
    if found is None:
        raise SystemExit("no freeze-candidate artefact: run `hyposense dev artifact` first")
    return found


def cmd_dev_artifact(args: argparse.Namespace) -> int:
    from hyposense.evaluation.s7_artifact import build_dev_artifact

    _print(build_dev_artifact(args.level))
    return 0


def cmd_dev_s7(args: argparse.Namespace) -> int:
    from hyposense.evaluation.s7_bench import run_s7_bench

    _print(run_s7_bench(_latest_model(args.model)))
    return 0


def cmd_dev_r4(args: argparse.Namespace) -> int:
    from hyposense.evaluation.r4_tuning import run_r4

    _print(run_r4(workers=args.workers))
    return 0


def cmd_dev_candidate(args: argparse.Namespace) -> int:
    from hyposense.evaluation.candidate import run_candidate

    _print(run_candidate(workers=args.workers))
    return 0


def cmd_dev_prefreeze(args: argparse.Namespace) -> int:
    from hyposense.evaluation.prefreeze import run_prefreeze

    _print(run_prefreeze(workers=args.workers))
    return 0


def cmd_dev_evidence(args: argparse.Namespace) -> int:
    from hyposense.evaluation.s8_evidence import build_evidence

    _print(build_evidence())
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from hyposense.api.app import create_app
    from hyposense.api.service import Service
    from hyposense.models.artifact import ArtifactError

    try:
        svc = Service(
            _latest_model(args.model),
            expected_manifest_sha256=args.expect_sha,
        )
    except ArtifactError as exc:
        print(f"REFUSING TO START: {exc}")
        return 3
    uvicorn.run(create_app(svc), host=args.host, port=args.port, log_level="info")
    return 0


def cmd_dev_s6(args: argparse.Namespace) -> int:
    from hyposense.evaluation.s6_run import run_s6

    _print(run_s6(workers=args.workers, resamples=args.resamples, trials=args.trials))
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    from hyposense.freeze import freeze

    if args.no_tests and not args.check:
        print("ERROR — FREEZE ABORTED: the test suite is mandatory for a freeze", file=sys.stderr)
        return 2
    report = freeze(write=not args.check, run_tests=not args.no_tests)
    _print(report)
    return 0 if report["errors"] == 0 else 2


def cmd_gates_show(args: argparse.Namespace) -> int:
    from hyposense.audit.gates import gates_dir

    d = gates_dir()
    files = sorted(d.glob("G*.json")) if d.exists() else []
    if not files:
        print("no gate results yet (run `hyposense audit run`)")
        return 1
    for f in files:
        g = json.loads(f.read_text(encoding="utf-8"))
        print(
            f"{g['gate']}: {g['status']}  ({g['title']}; evaluated {g['evaluated_utc']}, "
            f"commit {str(g['provenance']['git']['commit'])[:10]})"
        )
        for c in g["checks"]:
            print(f"   [{c['status']:>7}] {c['id']}: {c['summary']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hyposense", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--version", action="version", version=f"hyposense {__version__}")
    sub = p.add_subparsers(dest="group", required=True)

    data = sub.add_parser("data", help="official data acquisition and integrity").add_subparsers(
        dest="cmd", required=True
    )
    f = data.add_parser("fetch", help="download and verify the pinned archive")
    f.add_argument("--version", type=int, default=None, help="figshare version (default canonical)")
    f.add_argument("--force", action="store_true", help="re-download even if present")
    f.set_defaults(func=cmd_data_fetch)
    e = data.add_parser("extract", help="extract T2DM files from the canonical archive")
    e.add_argument("--overwrite", action="store_true")
    e.set_defaults(func=cmd_data_extract)
    m = data.add_parser("manifest", help="verify (default) or write data/MANIFEST.json")
    m.add_argument("--write", action="store_true")
    m.add_argument("--force", action="store_true")
    m.set_defaults(func=cmd_data_manifest)
    data.add_parser("validate", help="load every recording; summarise issues").set_defaults(
        func=cmd_data_validate
    )

    part = sub.add_parser("partition", help="T/E partition").add_subparsers(
        dest="cmd", required=True
    )
    part.add_parser("verify", help="check pinned hash and patient-set agreement").set_defaults(
        func=cmd_partition_verify
    )

    audit = sub.add_parser("audit", help="structural audit and gates").add_subparsers(
        dest="cmd", required=True
    )
    a = audit.add_parser("run", help="structural audit + reconciliation + G0/G1")
    a.add_argument(
        "--skip-versions",
        action="store_true",
        help="skip figshare version reconciliation (offline)",
    )
    a.set_defaults(func=cmd_audit_run)
    ev = audit.add_parser("events", help="labels + event audit + legacy reproduction + G2/G3b")
    ev.add_argument(
        "--skip-versions", action="store_true", help="skip legacy (figshare v1/v2) reproduction"
    )
    ev.set_defaults(func=cmd_audit_events)
    audit.add_parser("medication", help="medication audit, G3, G2 re-check").set_defaults(
        func=cmd_audit_medication
    )

    af = audit.add_parser("features", help="S4 feature audit on the tuning partition")
    af.add_argument("--workers", type=int, default=None, help="worker processes (default cpus-1)")
    af.set_defaults(func=cmd_audit_features)

    feats = sub.add_parser("features", help="feature specification").add_subparsers(
        dest="cmd", required=True
    )
    feats.add_parser("spec", help="write artifacts/features/feature_spec.json").set_defaults(
        func=cmd_features_spec
    )

    ev_ = sub.add_parser("eval", help="evaluation harness (S5)").add_subparsers(
        dest="cmd", required=True
    )
    em = ev_.add_parser("m0", help="Table A.2 reproduction + M0 on v5 T (DEVELOPMENT)")
    em.add_argument("--resamples", type=int, default=None, help="bootstrap resamples (config)")
    em.set_defaults(func=cmd_eval_m0)
    ev_.add_parser("registry", help="write the metric registry").set_defaults(
        func=cmd_eval_registry
    )

    dv = sub.add_parser("dev", help="development experiments on T (S6)").add_subparsers(
        dest="cmd", required=True
    )
    d6 = dv.add_parser("s6", help="M1 tuning, ladder, pre-registered experiments (T only)")
    d6.add_argument("--workers", type=int, default=None)
    d6.add_argument("--resamples", type=int, default=None, help="smoke tests only")
    d6.add_argument("--trials", type=int, default=None, help="smoke tests only")
    d6.set_defaults(func=cmd_dev_s6)
    da = dv.add_parser("artifact", help="S7 DEVELOPMENT model artefact (T only)")
    da.add_argument("--level", default="M3", choices=["M1", "M2", "M3r", "M3"])
    da.set_defaults(func=cmd_dev_artifact)
    d7 = dv.add_parser("s7", help="S7 engineering evidence on T")
    d7.add_argument("--model", default=None)
    d7.set_defaults(func=cmd_dev_s7)
    dr = dv.add_parser("r4", help="R4 per-model tuning on T (frozen before E; ANALYSIS_PLAN §5.7)")
    dr.add_argument("--workers", type=int, default=4)
    dr.set_defaults(func=cmd_dev_r4)
    dc = dv.add_parser(
        "candidate", help="freeze-candidate workflow (T only): gate, eval, artefact, replay"
    )
    dc.add_argument("--workers", type=int, default=4)
    dc.set_defaults(func=cmd_dev_candidate)
    dp = dv.add_parser("prefreeze", help="P-B10/P-B11/P-B12 pre-freeze Class B runs (T only)")
    dp.add_argument("--workers", type=int, default=6)
    dp.set_defaults(func=cmd_dev_prefreeze)
    d8 = dv.add_parser("evidence", help="aggregate Evidence View curves from the S6 OOF (T)")
    d8.set_defaults(func=cmd_dev_evidence)
    sv = sub.add_parser("serve", help="replay API (FastAPI + SSE), offline")
    sv.add_argument("--model", default=None)
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--expect-sha", default=None, help="pin the artefact manifest SHA-256")
    sv.set_defaults(func=cmd_serve)

    fz = sub.add_parser("freeze", help="protocol freeze (fails closed; never touches E)")
    fz.add_argument("--check", action="store_true", help="evaluate invariants; write nothing")
    fz.add_argument("--no-tests", action="store_true", help="skip the test suite (check only)")
    fz.set_defaults(func=cmd_freeze)
    gates = sub.add_parser("gates", help="gate results").add_subparsers(dest="cmd", required=True)
    gates.add_parser("show", help="print latest gate results").set_defaults(func=cmd_gates_show)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["Path", "build_parser", "main"]
