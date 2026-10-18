"""Versioned drug dictionary (configs/drug_dictionary.csv) and deterministic text normalisation."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from hyposense.common.config import CONFIG_DIR
from hyposense.common.hashing import sha256_file

DICTIONARY_PATH = CONFIG_DIR / "drug_dictionary.csv"
_SPACES = re.compile(
    "[\\s\u00a0\u2000-\u200b\u3000]+"
)  # any whitespace incl. NBSP, en/em spaces, ZWSP, ideographic


def normalise_text(text: str) -> str:
    """Lowercase; every unicode space (incl. NBSP, ideographic) → one ASCII space; trimmed."""
    return _SPACES.sub(" ", text.replace("\uff0c", ",").replace("\uff1b", ";")).strip().lower()


@dataclass(frozen=True)
class DrugEntry:
    alias: str
    canonical: str
    drug_class: str
    subclass: str
    route: str
    formulation: str
    dose_unit: str
    target: bool
    exposure_family: str
    kernel_components: str
    plausible_min: float | None
    plausible_max: float | None
    mapping_status: str
    notes: str

    @property
    def components(self) -> list[str]:
        """Canonical component drugs of a fixed-dose combination, in written order."""
        if not self.canonical.startswith("COMBINATION:"):
            return [self.canonical]
        return self.canonical.split(":", 1)[1].split("+")


@dataclass(frozen=True)
class DrugDictionary:
    entries: tuple[DrugEntry, ...]
    sha256: str

    def by_canonical(self, canonical: str) -> DrugEntry:
        return next(e for e in self.entries if e.canonical == canonical)

    @property
    def alias_regex(self) -> re.Pattern[str]:
        return _alias_regex(tuple(e.alias for e in self.entries))

    def lookup(self, alias: str) -> DrugEntry:
        return next(e for e in self.entries if e.alias == alias)


@lru_cache(maxsize=8)
def _alias_regex(aliases: tuple[str, ...]) -> re.Pattern[str]:
    # longest alias first so 'insulin aspart 70/30' wins over 'insulin aspart'
    ordered = sorted(aliases, key=lambda a: (-len(a), a))
    body = "|".join(re.escape(a) for a in ordered)
    return re.compile(rf"(?<![a-z0-9])({body})(?![a-z0-9])")


def _num(v: str) -> float | None:
    return float(v) if v.strip() else None


def load_dictionary(path: Path = DICTIONARY_PATH) -> DrugDictionary:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    entries = []
    for r in rows:
        alias = normalise_text(r["alias"])
        if alias != r["alias"]:
            raise ValueError(f"dictionary alias not normalised: {r['alias']!r}")
        entries.append(
            DrugEntry(
                alias=alias,
                canonical=r["canonical"],
                drug_class=r["drug_class"],
                subclass=r["subclass"],
                route=r["route"],
                formulation=r["formulation"],
                dose_unit=r["dose_unit"],
                target=r["target"] == "1",
                exposure_family=r["exposure_family"],
                kernel_components=r["kernel_components"],
                plausible_min=_num(r["plausible_min"]),
                plausible_max=_num(r["plausible_max"]),
                mapping_status=r["mapping_status"],
                notes=r["notes"],
            )
        )
    aliases = [e.alias for e in entries]
    if len(aliases) != len(set(aliases)):
        raise ValueError("duplicate aliases in drug dictionary")
    return DrugDictionary(entries=tuple(entries), sha256=sha256_file(path))
