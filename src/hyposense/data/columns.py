"""Canonical column schema for ShanghaiT2DM recording workbooks.

Headers are matched against an explicit table of known variants after whitespace
normalisation. Prefix heuristics are deliberately avoided: an unknown header is an error, never
a silent guess (Blueprint §10.1). The variants were catalogued from all 109 files of figshare v5
on 2026-10-18 (five distinct header tuples).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical columns in output order. ts_local = naive local timestamp from the "Date" column.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "ts_local",
    "cgm",
    "cbg",
    "ketone",
    "diet_en",
    "diet_cn",
    "insulin_sc",
    "oral_agents",
    "csii_bolus",
    "csii_basal",
    "insulin_iv",
)
REQUIRED_COLUMNS = frozenset({"ts_local", "cgm"})
NUMERIC_COLUMNS = ("cgm", "cbg", "ketone", "csii_bolus", "csii_basal")
TEXT_COLUMNS = ("diet_en", "diet_cn", "insulin_sc", "oral_agents", "insulin_iv")

# Units implied by each canonical column. A header without a unit is interpreted with the same
# unit (ASSUMPTION, verified by the structural audit's per-variant value ranges).
UNITS: dict[str, str] = {
    "cgm": "mg/dL",
    "cbg": "mg/dL",
    "ketone": "mmol/L",
    "csii_bolus": "IU",
    "csii_basal": "IU/h",
}

# normalised header -> (canonical column, header states its unit explicitly)
HEADER_VARIANTS: dict[str, tuple[str, bool]] = {
    "Date": ("ts_local", True),
    "CGM (mg / dl)": ("cgm", True),
    "CGM": ("cgm", False),
    "CBG (mg / dl)": ("cbg", True),
    "CBG": ("cbg", False),
    "Blood Ketone (mmol / L)": ("ketone", True),
    "Blood Ketone": ("ketone", False),
    "Dietary intake": ("diet_en", True),
    "饮食": ("diet_cn", True),
    "进食量": ("diet_cn", True),
    "Insulin dose - s.c.": ("insulin_sc", True),
    "Non-insulin hypoglycemic agents": ("oral_agents", True),
    "CSII - bolus insulin (Novolin R, IU)": ("csii_bolus", True),
    "CSII - bolus insulin (Novolin R IU)": ("csii_bolus", True),
    "CSII - bolus insulin": ("csii_bolus", False),
    "CSII - basal insulin (Novolin R, IU / H)": ("csii_basal", True),
    "CSII - basal insulin (Novolin R IU / H)": ("csii_basal", True),
    "CSII - basal insulin": ("csii_basal", False),
    "胰岛素泵基础量 (Novolin R, IU / H)": ("csii_basal", True),
    "Insulin dose - i.v.": ("insulin_iv", True),
}

_WS = re.compile(r"\s+")


class SchemaError(ValueError):
    """A workbook's columns cannot be mapped to the canonical schema."""


def normalise_header(header: object) -> str:
    return _WS.sub(" ", str(header)).strip()


@dataclass(frozen=True)
class ColumnMapping:
    raw_headers: tuple[str, ...]
    to_canonical: dict[str, str]  # raw header -> canonical column
    absent: tuple[str, ...]  # canonical columns not present in this file
    unitless: tuple[str, ...]  # canonical columns whose header carried no unit

    @property
    def variant_id(self) -> str:
        """Stable identifier of the header tuple (used to count variants)."""
        return "|".join(normalise_header(h) for h in self.raw_headers)


def map_columns(headers: list[object] | tuple[object, ...]) -> ColumnMapping:
    raw = tuple(str(h) for h in headers)
    mapping: dict[str, str] = {}
    unitless: list[str] = []
    unknown = []
    for h in raw:
        key = normalise_header(h)
        if key not in HEADER_VARIANTS:
            unknown.append(h)
            continue
        canon, explicit_unit = HEADER_VARIANTS[key]
        if canon in mapping.values():
            raise SchemaError(f"two headers map to {canon!r}: {raw}")
        mapping[h] = canon
        if not explicit_unit:
            unitless.append(canon)
    if unknown:
        raise SchemaError(
            f"unknown column header(s) {unknown!r}; add to HEADER_VARIANTS only "
            "after confirming meaning and units"
        )
    missing_required = REQUIRED_COLUMNS - set(mapping.values())
    if missing_required:
        raise SchemaError(f"required column(s) missing: {sorted(missing_required)}")
    absent = tuple(c for c in CANONICAL_COLUMNS if c not in mapping.values())
    return ColumnMapping(raw, mapping, absent, tuple(unitless))
