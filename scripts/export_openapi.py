"""Write frontend/openapi.json from the FastAPI app (ADR-008: frontend types are generated from it).

Usage: uv run python scripts/export_openapi.py  (then: cd frontend && npm run gen:types)
"""

from __future__ import annotations

import json
from typing import Any

from hyposense.api.app import create_app
from hyposense.common.config import REPO_ROOT


def main() -> None:
    app = create_app(svc=Any, clock=False)  # type: ignore[arg-type]  # schema only; no service
    out = REPO_ROOT / "frontend" / "openapi.json"
    out.write_text(
        json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n", "utf-8", newline="\n"
    )
    print(out)


if __name__ == "__main__":
    main()
