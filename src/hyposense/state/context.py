"""Static context of one recording (Blueprint Table 25.1 PatientStatic; App. D group 5).

The summary sheet has ONE ROW PER RECORDING. A patient with several recordings may have
different values in each row (MEASURED on T: weight, HbA1c, eGFR and C-peptide differ for 2 of
3 multi-recording patients). Each recording therefore uses its own row.

**Temporal status (protocol, Blueprint §10.2; SA8).** Laboratory values (HbA1c, eGFR, fasting
C-peptide) may have been measured up to six months before or after the CGM period. They are
patient-level context, not time-stamped events. They are constant over the recording and
available at every t. This is the accepted, documented residual risk; SA8 removes them. They are
never reinterpreted as time-varying information.

Allow-list, not deny-list: only the fields below are read. "Hypoglycemia (yes/no)" and patient
identifiers are never read (`FORBIDDEN_FEATURE_COLUMNS`). Missing values ("/" in the sheet,
blank, unparseable or outside the plausible range) become NaN, never 0, and are counted in
`issues`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from hyposense.data.summary import FORBIDDEN_FEATURE_COLUMNS
from hyposense.medication.dictionary import DrugDictionary
from hyposense.medication.recording import prescribed_drugs

# context field -> summary column (allow-list)
STATIC_FIELDS: dict[str, str] = {
    "age_y": "age_y",
    "sex_male": "sex_code",
    "bmi": "bmi",
    "weight_kg": "weight_kg",
    "diabetes_duration_y": "duration_y",
    "hba1c_mmol_mol": "hba1c_mmol_mol",
    "egfr": "egfr",
    "c_peptide_fasting_nmol_l": "c_peptide_fasting_nmol_l",
}
LAB_FIELDS = frozenset({"hba1c_mmol_mol", "egfr", "c_peptide_fasting_nmol_l"})  # SA8
REGIMEN_COLUMN = "prescribed_hypoglycemic_agents"
MISSING_MARKERS = frozenset({"", "/", "-", "--", "na", "n/a", "none"})
assert not (set(STATIC_FIELDS.values()) | {REGIMEN_COLUMN}) & FORBIDDEN_FEATURE_COLUMNS

# App. D group 5 prescribed-regimen flags -> predicate on (drug_class, subclass)
REGIMEN_FLAGS: dict[str, tuple[str, frozenset[str] | None]] = {
    "rx_insulin": ("insulin", None),
    "rx_premix": ("insulin", frozenset({"premix_analogue", "premix_human"})),
    "rx_basal": ("insulin", frozenset({"basal_analogue", "intermediate_human"})),
    "rx_short_rapid": ("insulin", frozenset({"rapid_analogue", "short_human"})),
    "rx_su": ("sulfonylurea", None),
    "rx_glinide": ("glinide", None),
    "rx_metformin": ("biguanide", None),
    "rx_agi": ("agi", None),
    "rx_dpp4": ("dpp4", None),
    "rx_sglt2": ("sglt2", None),
    "rx_glp1": ("glp1", None),
    "rx_tzd": ("tzd", None),
}


@dataclass(frozen=True)
class PatientContext:
    patient_key: str
    recording_key: str
    values: dict[str, float]  # STATIC_FIELDS -> value (NaN = missing)
    regimen: dict[str, float]  # REGIMEN_FLAGS -> 0/1, NaN if the regimen field is empty
    prescribed_classes: frozenset[str]  # drug classes named in the regimen (exposure rule)
    issues: tuple[str, ...] = ()  # field: reason, for values set to missing

    @classmethod
    def unknown(cls, patient_key: str, recording_key: str) -> PatientContext:
        """No summary row: every static value is missing (never zero)."""
        return cls(
            patient_key,
            recording_key,
            {k: math.nan for k in STATIC_FIELDS},
            {k: math.nan for k in REGIMEN_FLAGS},
            frozenset(),
            ("summary_row: absent",),
        )


def _number(raw: object) -> tuple[float, str | None]:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return math.nan, "missing"
    if isinstance(raw, bool):
        return math.nan, "unparseable"
    if isinstance(raw, int | float):
        return float(raw), None
    s = str(raw).strip()
    if s.lower() in MISSING_MARKERS:
        return math.nan, "missing"
    try:
        return float(s), None
    except ValueError:
        return math.nan, "unparseable"


def parse_context(
    patient_key: str,
    recording_key: str,
    row: Mapping[str, object] | None,
    d: DrugDictionary,
    plausible: Mapping[str, tuple[float, float]],
) -> PatientContext:
    if row is None:
        return PatientContext.unknown(patient_key, recording_key)
    values: dict[str, float] = {}
    issues: list[str] = []
    for name, col in STATIC_FIELDS.items():
        v, problem = _number(row.get(col))
        if name == "sex_male" and problem is None:
            v, problem = {1.0: (0.0, None), 2.0: (1.0, None)}.get(v, (math.nan, "invalid_code"))
        if problem is None and name in plausible:
            lo, hi = plausible[name]
            if not lo <= v <= hi:
                v, problem = math.nan, "implausible"
        if problem is not None:
            issues.append(f"{name}: {problem}")
        values[name] = v
    drugs = prescribed_drugs(row.get(REGIMEN_COLUMN), d)
    if drugs is None:
        regimen = {k: math.nan for k in REGIMEN_FLAGS}
        classes: frozenset[str] = frozenset()
        issues.append("regimen: missing")
    else:
        entries = [d.by_canonical(c) for c in drugs]
        classes = frozenset(e.drug_class for e in entries)
        regimen = {
            flag: float(
                any(e.drug_class == cls and (sub is None or e.subclass in sub) for e in entries)
            )
            for flag, (cls, sub) in REGIMEN_FLAGS.items()
        }
    return PatientContext(patient_key, recording_key, values, regimen, classes, tuple(issues))
