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

LIVE_PATH = ["data", "medication", "state", "features", "models", "calibration", "policy",
             "replay", "api"]
FORBIDDEN_FOR_LIVE = {"hyposense.labels", "hyposense.evaluation"}
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
    for sub in [*LIVE_PATH, "labels", "evaluation", "common"]:
        assert (PKG / sub / "__init__.py").is_file(), sub
