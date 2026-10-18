"""`hyposense` command-line interface (cross-platform replacement for Makefile targets, ADR-006).

hyposense data fetch [--version N]      download + verify the pinned figshare archive
hyposense data extract [--overwrite]    extract allow-listed T2DM files from the canonical archive
hyposense data manifest [--write]       verify (default) or create data/MANIFEST.json
hyposense data validate                 manifest check + load every recording; issue summary
hyposense partition verify              pinned hash, patient-set agreement, counts
hyposense audit run                     structural audit + version reconciliation + G0/G1
hyposense audit events                  labels, event audit, legacy reproduction, G2/G3b
hyposense audit medication              medication audit, G3, G2 re-check (production treated)
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
