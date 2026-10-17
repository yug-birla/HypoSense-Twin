"""Shared test fixtures.

SYNTHETIC fixtures: every workbook built here is synthetic test data generated at test time,
never real patient data. Tests marked `requires_data` need the official copy under data/raw and
skip cleanly without it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_PRESENT = (REPO_ROOT / "data" / "raw" / "ShanghaiT2DM" / "Shanghai_T2DM").is_dir()

STANDARD_HEADERS = (
    "Date",
    "CGM (mg / dl)",
    "CBG (mg / dl)",
    "Blood Ketone (mmol / L)",
    "Dietary intake",
    "饮食",
    "Insulin dose - s.c.",
    "Non-insulin hypoglycemic agents",
    "CSII - bolus insulin (Novolin R, IU)",
    "CSII - basal insulin (Novolin R, IU / H)",
    "Insulin dose - i.v.",
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if DATA_PRESENT:
        return
    skip = pytest.mark.skip(reason="official ShanghaiT2DM copy not present under data/raw")
    for item in items:
        if "requires_data" in item.keywords:
            item.add_marker(skip)


WorkbookFactory = Callable[..., Path]


@pytest.fixture
def make_workbook(tmp_path: Path) -> WorkbookFactory:
    """Write a SYNTHETIC .xlsx recording. rows: sequences aligned with headers."""

    def _make(
        name: str,
        rows: Sequence[Sequence[Any]],
        headers: Sequence[str] = STANDARD_HEADERS,
        sheet_name: str | None = None,
        extra_sheets: Sequence[str] = (),
        directory: Path | None = None,
    ) -> Path:
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = sheet_name or name.rsplit(".", 1)[0]
        ws.append(list(headers))
        for r in rows:
            ws.append(list(r))
        for extra in extra_sheets:
            wb.create_sheet(extra)
        out = (directory or tmp_path) / name
        out.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out)
        return out

    return _make


def row(ts: datetime | str | None, cgm: Any = None, **kw: Any) -> list[Any]:
    """Build one SYNTHETIC row in STANDARD_HEADERS order."""
    return [
        ts,
        cgm,
        kw.get("cbg"),
        kw.get("ketone"),
        kw.get("diet_en"),
        kw.get("diet_cn"),
        kw.get("insulin_sc"),
        kw.get("oral"),
        kw.get("csii_bolus"),
        kw.get("csii_basal"),
        kw.get("iv"),
    ]
