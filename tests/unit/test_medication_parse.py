"""Medication normalisation, dose parsing and treated-status tests (SYNTHETIC cells; the raw
strings mirror the formats catalogued in the S3 vocabulary inventory)."""

from __future__ import annotations

import pytest

from hyposense.common.config import load_config
from hyposense.medication.dictionary import load_dictionary, normalise_text
from hyposense.medication.events import EventKind, Flag, ParseStatus
from hyposense.medication.parse import Context, parse_cell
from hyposense.medication.recording import (
    RecordingMedication,
    prescribed_classes,
    treatment_status,
)

D = load_dictionary()
RULES = load_config("pharma.yaml")["formulation_rules"]


def _parse(value: object, column: str):  # type: ignore[no-untyped-def]
    ctx = Context("shanghai_t2dm:2001", "2001_0_20210301", 1_600_000_000, column, 2, str(value))
    return parse_cell(value, column, ctx, D, RULES)


def _one(value: object, column: str):  # type: ignore[no-untyped-def]
    ev = _parse(value, column).events
    assert len(ev) == 1, ev
    return ev[0]


def test_normalisation() -> None:
    assert normalise_text("insulin\xa0glargine, 18 IU ") == "insulin glargine, 18 iu"
    assert normalise_text("  Humulin 70/30  8 IU") == "humulin 70/30 8 iu"
    assert normalise_text("metformin 0.5 g\uff0c acarbose") == "metformin 0.5 g, acarbose"


@pytest.mark.parametrize(
    ("text", "canonical", "dose", "family"),
    [
        ("insulin aspart 70/30, 14 IU", "insulin_aspart_biphasic_30", 14.0, "insulin_premix"),
        ("insulin aspart 70/30, 8 IU ", "insulin_aspart_biphasic_30", 8.0, "insulin_premix"),
        ("insulin aspart, 5 IU", "insulin_aspart", 5.0, "insulin_rapid"),
        ("insulin glulisine, 6 IU", "insulin_glulisine", 6.0, "insulin_rapid"),
        ("Humulin 70/30  8 IU", "premix_human_30_70", 8.0, "insulin_premix"),
        ("Novolin 30R, 14 IU", "premix_human_30_70", 14.0, "insulin_premix"),
        ("SciLin M30, 25 IU", "premix_human_30_70", 25.0, "insulin_premix"),
        ("Gansulin 40R, 10 IU", "premix_human_40_60", 10.0, "insulin_premix"),
        ("Novolin R, 10 IU", "regular_human_insulin", 10.0, "insulin_regular"),
        ("Gansulin R, 4 IU", "regular_human_insulin", 4.0, "insulin_regular"),
        ("insulin glargine, 6 IU", "insulin_glargine", 6.0, "insulin_basal"),
        ("insulin\xa0glargine, 18 IU", "insulin_glargine", 18.0, "insulin_basal"),
        ("insulin glarigine, 12 IU", "insulin_glargine", 12.0, "insulin_basal"),
        ("insulin detemir, 15 IU", "insulin_detemir", 15.0, "insulin_basal"),
        ("insulin degludec, 6 IU", "insulin_degludec", 6.0, "insulin_basal"),
    ],
)
def test_insulin_sc_parses(text: str, canonical: str, dose: float, family: str) -> None:
    e = _one(text, "insulin_sc")
    assert (e.canonical, e.dose, e.dose_unit, e.exposure_family) == (canonical, dose, "IU", family)
    assert e.parse_status is ParseStatus.PARSED and e.route == "sc" and e.target
    assert e.is_target_administration


def test_premix_kernel_weights() -> None:
    assert (
        _one("insulin aspart 70/30, 14 IU", "insulin_sc").kernel_components
        == "rapid_analogue:0.30;intermediate_nph:0.70"
    )
    assert (
        _one("Gansulin 40R, 10 IU", "insulin_sc").kernel_components
        == "regular_human:0.40;intermediate_nph:0.60"
    )


def test_two_products_in_one_cell() -> None:
    ev = _parse("insulin glargine, 14 IU, Humulin 70/30, 12 IU", "insulin_sc").events
    assert [(e.canonical, e.dose) for e in ev] == [
        ("insulin_glargine", 14.0),
        ("premix_human_30_70", 12.0),
    ]


@pytest.mark.parametrize(
    ("text", "status", "flags"),
    [
        ("Novolin R", ParseStatus.PARSED_WITH_WARNING, {Flag.DOSE_UNKNOWN}),
        ("Novolin R, 8", ParseStatus.PARSED_WITH_WARNING, {Flag.DOSE_UNKNOWN, Flag.UNIT_MISSING}),
        ("Novolin R, 8 IU 10 IU", ParseStatus.AMBIGUOUS, {Flag.MULTIPLE_DOSE_CANDIDATES}),
        ("Novolin R, 90 IU", ParseStatus.PARSED_WITH_WARNING, {Flag.DOSE_IMPLAUSIBLE}),
    ],
)
def test_insulin_dose_problems_are_flagged_never_invented(
    text: str, status: ParseStatus, flags: set[Flag]
) -> None:
    e = _one(text, "insulin_sc")
    assert e.parse_status is status and flags <= set(e.flags)
    if Flag.DOSE_IMPLAUSIBLE not in flags:
        assert e.dose is None


def test_unknown_product_is_unparseable() -> None:
    ev = _parse("mysteryin, 8 IU", "insulin_sc").events
    assert [e.parse_status for e in ev] == [ParseStatus.UNPARSEABLE]
    assert _parse("mysteryin, 8 IU", "insulin_sc").status is ParseStatus.UNPARSEABLE


@pytest.mark.parametrize(
    ("text", "canonical", "dose", "status"),
    [
        ("metformin 0.5 g", "metformin", 500.0, ParseStatus.NON_TARGET_MEDICATION),
        ("metformin 850 mg", "metformin", 850.0, ParseStatus.NON_TARGET_MEDICATION),
        ("acarbose 50 mg", "acarbose", 50.0, ParseStatus.NON_TARGET_MEDICATION),
        ("glimepiride 2 mg", "glimepiride", 2.0, ParseStatus.PARSED),
        ("gliquidone 15 mg", "gliquidone", 15.0, ParseStatus.PARSED),
        ("repaglinide 0.5 mg", "repaglinide", 0.5, ParseStatus.PARSED),
        ("liraglutide 1.2 mg", "liraglutide", 1.2, ParseStatus.NON_TARGET_MEDICATION),
    ],
)
def test_oral_column_parses(text: str, canonical: str, dose: float, status: ParseStatus) -> None:
    e = _one(text, "oral_agents")
    assert (e.canonical, e.dose, e.dose_unit, e.parse_status) == (canonical, dose, "mg", status)
    if canonical == "liraglutide":
        assert e.route == "sc"  # injectable in the non-insulin agents column (not misplaced)
        assert Flag.MISPLACED_COLUMN not in e.flags


@pytest.mark.parametrize(
    ("dose", "formulation", "basis", "kernel", "status"),
    [
        (30, "modified-release", "DOSE_RULE", "bateman:gliclazide_mr", ParseStatus.PARSED),
        (120, "modified-release", "DOSE_RULE", "bateman:gliclazide_mr", ParseStatus.PARSED),
        (
            15,
            "modified-release",
            "INFERRED",
            "bateman:gliclazide_mr",
            ParseStatus.PARSED_WITH_WARNING,
        ),
        (40, "immediate-release", "DOSE_RULE", "bateman:gliclazide_ir", ParseStatus.PARSED),
        (50, "unknown", "UNKNOWN", "bateman:gliclazide", ParseStatus.PARSED_WITH_WARNING),
    ],
)
def test_gliclazide_formulation_rule(
    dose: int, formulation: str, basis: str, kernel: str, status: ParseStatus
) -> None:
    e = _one(f"gliclazide {dose} mg", "oral_agents")
    assert (e.formulation, e.formulation_basis, e.kernel_components, e.parse_status) == (
        formulation,
        basis,
        kernel,
        status,
    )


def test_implausible_units_are_kept_and_flagged() -> None:
    e = _one("\xa0voglibose 0.2 g", "oral_agents")
    assert e.dose == 200.0 and Flag.DOSE_IMPLAUSIBLE in e.flags  # not "corrected" to 0.2 mg


def test_compound_and_combination_strings() -> None:
    ev = _parse("metformin 500 mg,  voglibose 0.2 mg", "oral_agents").events
    assert [(e.canonical, e.dose) for e in ev] == [("metformin", 500.0), ("voglibose", 0.2)]
    ev = _parse(
        "sitagliptinphosphate/metforminhydrochloride tablets 50 mg / 500 mg", "oral_agents"
    ).events
    assert [(e.canonical, e.dose) for e in ev] == [("sitagliptin", 50.0), ("metformin", 500.0)]
    assert all(Flag.COMBINATION_PRODUCT in e.flags for e in ev)
    ev = _parse("sitagliptin 100 mg, gliclazide 15 mg, acarbose 50 mg", "oral_agents").events
    assert [e.canonical for e in ev] == ["sitagliptin", "gliclazide", "acarbose"]


def test_iv_column_is_content_aware() -> None:
    ev = _parse(
        "500ml 0.9% sodium chloride, 15 IU Novolin R, 10 ml 10% potassium chloride", "insulin_iv"
    ).events
    assert [(e.kind, e.canonical) for e in ev] == [
        (EventKind.IV_FLUID, "sodium_chloride"),
        (EventKind.ADMINISTRATION, "regular_human_insulin"),
        (EventKind.IV_FLUID, "potassium_chloride"),
    ]
    ins = ev[1]
    assert ins.route == "iv" and ins.dose == 15.0 and Flag.RATE_UNKNOWN in ins.flags
    assert ins.is_target_administration and ins.kernel_components is None
    assert (ev[0].dose, ev[0].concentration_pct) == (500.0, 0.9)
    g = _parse(
        "250 ml 5% glucose and sodium chloride, 6 IU Novolin R,  5 ml 10% potassium chloride",
        "insulin_iv",
    ).events[0]
    assert g.canonical == "glucose_sodium_chloride" and Flag.GLUCOSE_INFUSION in g.flags
    assert not g.target


def test_header_artefact_in_iv_column() -> None:
    e = _one("CSII - basal insulin (Novolin R, IU / H)", "insulin_iv")
    assert e.parse_status is ParseStatus.NON_MEDICATION and Flag.HEADER_ARTEFACT in e.flags
    assert not e.is_target_administration


def test_csii_cells() -> None:
    b = _one(6.0, "csii_bolus")
    assert (b.canonical, b.route, b.dose, b.parse_status) == (
        "regular_human_insulin",
        "csii",
        6.0,
        ParseStatus.PARSED,
    )
    z = _one(0.0, "csii_bolus")
    assert Flag.ZERO_DOSE in z.flags and not z.is_target_administration
    r = _one(0.4, "csii_basal")
    assert (r.kind, r.dose, r.dose_unit) == (EventKind.PUMP_BASAL_RATE, 0.4, "IU/h")
    assert r.is_target_administration
    assert not _one(0.0, "csii_basal").is_target_administration
    s = _one("temporarily suspend insulin delivery", "csii_basal")
    assert s.kind is EventKind.PUMP_SUSPEND and not s.is_target_administration
    a = _one("acarbose 50 mg", "csii_bolus")  # misplaced oral agent: classified by content
    assert (a.canonical, a.route, a.parse_status) == (
        "acarbose",
        "oral",
        ParseStatus.NON_TARGET_MEDICATION,
    )
    assert Flag.MISPLACED_COLUMN in a.flags and a.source_column == "csii_bolus"


def _rec(*cells: tuple[object, str]) -> RecordingMedication:
    evs = tuple(e for v, c in cells for e in _parse(v, c).events)
    return RecordingMedication("2001_0_20210301", "shanghai_t2dm:2001", (), evs, {})


@pytest.mark.parametrize(
    ("cells", "treated"),
    [
        ([("acarbose 50 mg", "csii_bolus")], False),  # the 2078 case (legacy said treated)
        ([("metformin 500 mg", "oral_agents")], False),
        ([(0.0, "csii_bolus")], False),
        ([("CSII - basal insulin (Novolin R, IU / H)", "insulin_iv")], False),
        ([(0.4, "csii_basal")], True),
        ([("Novolin R, 8 IU", "insulin_sc")], True),
        ([("Novolin R", "insulin_sc")], True),  # logged administration, dose unknown
        ([("gliclazide 30 mg", "oral_agents")], True),
        ([("repaglinide 0.5 mg", "oral_agents")], True),
        ([("500ml 0.9% sodium chloride, 8 IU Novolin R", "insulin_iv")], True),
    ],
)
def test_treatment_status(cells: list[tuple[object, str]], treated: bool) -> None:
    assert treatment_status([_rec(*cells)]).treated is treated


def test_prescribed_classes() -> None:
    assert prescribed_classes("metformin, gliclazide, insulin aspart 70/30", D) == frozenset(
        {"biguanide", "sulfonylurea", "insulin"}
    )
    assert prescribed_classes("none", D) == frozenset()
    assert prescribed_classes(None, D) == frozenset()


def test_dictionary_integrity() -> None:
    assert len(D.entries) == len({e.alias for e in D.entries})
    for e in D.entries:
        if e.target and e.drug_class == "insulin":
            assert (
                e.kernel_components
                and abs(sum(float(p.split(":")[1]) for p in e.kernel_components.split(";")) - 1.0)
                < 1e-9
            )
