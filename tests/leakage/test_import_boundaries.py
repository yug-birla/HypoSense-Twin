"""Static import-boundary guard (leakage and separation of concerns).

- Live-path modules must never import the label builder or the evaluation harness: those may
  look into the future, and features(t) may only use information available at or before t.
- The policy must not import model code (CLAUDE.md §19: model and policy stay separate).

Checked by parsing source, so it holds even before the modules are implemented.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / "src" / "hyposense"

LIVE_PATH = [
    "data",
    "medication",
    "state",
    "features",
    "models",
    "calibration",
    "policy",
    "replay",
    "api",
]
FORBIDDEN_FOR_LIVE = {"hyposense.labels", "hyposense.evaluation", "hyposense.audit"}
FORBIDDEN_EXTRA = {"policy": {"hyposense.models", "hyposense.calibration"}}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.parametrize("subpkg", LIVE_PATH)
def test_live_path_does_not_import_offline_modules(subpkg: str) -> None:
    forbidden = FORBIDDEN_FOR_LIVE | FORBIDDEN_EXTRA.get(subpkg, set())
    violations = []
    for py in sorted((PKG / subpkg).rglob("*.py")):
        for mod in _imports(py):
            if any(mod == f or mod.startswith(f + ".") for f in forbidden):
                violations.append(f"{py.relative_to(PKG)} imports {mod}")
    assert not violations, "\n".join(violations)


def test_all_planned_subpackages_exist() -> None:
    for sub in [*LIVE_PATH, "labels", "evaluation", "common", "audit"]:
        assert (PKG / sub / "__init__.py").is_file(), sub


# Sealed-partition safeguard (approved P-C5): the aggregate-audit scope, which can read E files,
# may be used only by the audit package, the CLI's validate command and its own definition.
AGGREGATE_SCOPE_ALLOWED = {"audit", "cli.py", "data/dataset.py"}


def test_aggregate_audit_scope_is_confined() -> None:
    offenders = []
    for py in sorted(PKG.rglob("*.py")):
        rel = py.relative_to(PKG).as_posix()
        if rel.split("/")[0] in AGGREGATE_SCOPE_ALLOWED or rel in AGGREGATE_SCOPE_ALLOWED:
            continue
        if "AGGREGATE_AUDIT" in py.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert not offenders, f"AGGREGATE_AUDIT used outside the audit: {offenders}"


def test_raw_partition_access_is_confined() -> None:
    """Only data/, audit/ and the partition import script may read the partition directly;
    modelling code must go through load_dataset(AccessScope.TUNING_ONLY)."""
    offenders = []
    for py in sorted(PKG.rglob("*.py")):
        rel = py.relative_to(PKG).as_posix()
        if rel.split("/")[0] in {"data", "audit"}:
            continue
        if "load_partition" in py.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert not offenders, offenders
