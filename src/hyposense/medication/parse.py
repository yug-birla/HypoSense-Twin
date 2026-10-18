"""Deterministic medication parsing (Blueprint §12.1, App. B; S3 brief §3.3-3.5).

Grammars, by source column (classification follows CONTENT; the source column is kept):
- insulin_sc   "<product>, <dose> IU" pairs; the comma may be missing; several pairs per cell.
- oral_agents  "<drug> <dose> <mg|g>" components separated by commas. Fixed-dose combinations
               ("A/B tablets 50 mg / 500 mg") are split into component events, doses in written
               order.
- insulin_iv   comma components: "<vol> ml <conc>% <fluid>" (saline, glucose, KCl) or
               "<dose> IU <insulin>". i.v. insulin is the amount in the bag; the rate is unknown.
- csii_bolus   number → regular-insulin bolus (IU). Text is parsed by content (e.g. a misplaced
               "acarbose 50 mg" becomes an oral event flagged MISPLACED_COLUMN).
- csii_basal   number → basal rate (IU/h). "temporarily suspend insulin delivery" → PUMP_SUSPEND.

Doses are never invented. A missing dose gives DOSE_UNKNOWN; two candidates give AMBIGUOUS. An
implausible dose is kept as written and flagged. Unit conversion is limited to g → mg.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from hyposense.medication.dictionary import DrugDictionary, DrugEntry, normalise_text
from hyposense.medication.events import EntryParse, EventKind, Flag, MedicationEvent, ParseStatus

_NUM = r"(\d+(?:\.\d+)?)"
_IU = re.compile(_NUM + r"\s*(?:iu|u|units?)\b")
_MASS = re.compile(_NUM + r"\s*(mg|g|mcg|ug|µg)\b")
_ML = re.compile(_NUM + r"\s*ml\b")
_PCT = re.compile(_NUM + r"\s*%")
_NOISE = re.compile(r"[\s,;/()\-.:]+|\btablets?\b")
PUMP_SUSPEND_TEXT = "temporarily suspend insulin delivery"
HEADER_TEXTS = ("csii - basal insulin (novolin r, iu / h)", "csii - bolus insulin (novolin r, iu)")
_TO_MG = {"mg": 1.0, "g": 1000.0, "mcg": 0.001, "ug": 0.001, "µg": 0.001}


@dataclass(frozen=True)
class Context:
    patient_key: str
    recording_key: str
    ts: int
    source_column: str
    source_row: int
    raw_text: str


def _base(
    ctx: Context, component: str, kind: EventKind, status: ParseStatus, **kw: Any
) -> MedicationEvent:
    return MedicationEvent(
        patient_key=ctx.patient_key,
        recording_key=ctx.recording_key,
        ts=ctx.ts,
        source_column=ctx.source_column,
        source_row=ctx.source_row,
        raw_text=ctx.raw_text,
        component_text=component,
        kind=kind,
        parse_status=status,
        **kw,
    )


def _from_entry(
    ctx: Context,
    component: str,
    e: DrugEntry,
    dose: float | None,
    unit: str | None,
    flags: list[Flag],
    formulation_rules: dict[str, Any],
    route: str | None = None,
    kind: EventKind = EventKind.ADMINISTRATION,
) -> MedicationEvent:
    flags = list(flags)
    formulation, basis, kernel = e.formulation, "DICTIONARY", e.kernel_components
    if e.formulation == "FORMULATION_RULE":
        formulation, basis, kernel, extra = apply_formulation_rule(
            e.canonical, dose, formulation_rules
        )
        flags += extra
    if dose is not None and dose == 0:
        flags.append(Flag.ZERO_DOSE)
    elif (
        dose is not None
        and e.plausible_min is not None
        and e.plausible_max is not None
        and not (e.plausible_min <= dose <= e.plausible_max)
    ):
        flags.append(Flag.DOSE_IMPLAUSIBLE)
    if not e.target:
        status = ParseStatus.NON_TARGET_MEDICATION
    elif Flag.MULTIPLE_DOSE_CANDIDATES in flags:
        status = ParseStatus.AMBIGUOUS
    elif flags:
        status = ParseStatus.PARSED_WITH_WARNING
    else:
        status = ParseStatus.PARSED
    return _base(
        ctx,
        component,
        kind,
        status,
        canonical=e.canonical,
        drug_class=e.drug_class,
        subclass=e.subclass,
        route=route or e.route,
        formulation=formulation,
        formulation_basis=basis,
        dose=dose,
        dose_unit=unit,
        target=e.target,
        exposure_family=e.exposure_family,
        kernel_components=kernel,
        flags=tuple(dict.fromkeys(flags)),
    )


def apply_formulation_rule(
    canonical: str, dose: float | None, rules: dict[str, Any]
) -> tuple[str, str, str, list[Flag]]:
    """Dose-based formulation inference (Blueprint App. B; ASSUMPTION, flagged when inferred)."""
    rule = rules.get(canonical)
    if rule is None or dose is None:
        return "unknown", "UNKNOWN", f"bateman:{canonical}", [Flag.FORMULATION_UNKNOWN]
    for _form, spec in rule.items():
        if dose in [float(x) for x in spec["doses"]]:
            flags = [Flag.FORMULATION_INFERRED] if spec["basis"] == "INFERRED" else []
            return spec["formulation"], spec["basis"], f"bateman:{spec['kernel']}", flags
    return "unknown", "UNKNOWN", f"bateman:{canonical}", [Flag.FORMULATION_UNKNOWN]


def _segments(text: str, d: DrugDictionary) -> tuple[str, list[tuple[DrugEntry, str]]]:
    """Split normalised text at alias matches → (leading text, [(entry, segment text)])."""
    matches = list(d.alias_regex.finditer(text))
    lead = text[: matches[0].start()] if matches else text
    out = []
    for k, m in enumerate(matches):
        end = matches[k + 1].start() if k + 1 < len(matches) else len(text)
        out.append((d.lookup(m.group(1)), text[m.start() : end]))
    return lead, out


def _residue(segment: str, alias: str, patterns: list[re.Pattern[str]]) -> str:
    rest = segment.replace(alias, " ", 1)
    for p in patterns:
        rest = p.sub(" ", rest)
    return _NOISE.sub("", rest)


def _unrecognised(ctx: Context, component: str) -> MedicationEvent:
    return _base(
        ctx,
        component,
        EventKind.UNRECOGNISED,
        ParseStatus.UNPARSEABLE,
        flags=(Flag.UNRECOGNISED_TEXT,),
    )


def parse_text(
    text: str, column: str, ctx: Context, d: DrugDictionary, formulation_rules: dict[str, Any]
) -> list[MedicationEvent]:
    norm = normalise_text(text)
    if norm == PUMP_SUSPEND_TEXT:
        status = ParseStatus.NON_MEDICATION if column != "csii_basal" else ParseStatus.PARSED
        return [
            _base(
                ctx,
                norm,
                EventKind.PUMP_SUSPEND,
                status,
                drug_class="insulin",
                route="csii",
                target=True,
                dose=0.0,
                dose_unit="IU/h",
            )
        ]
    if norm in HEADER_TEXTS:
        return [
            _base(
                ctx,
                norm,
                EventKind.NON_MEDICATION_TEXT,
                ParseStatus.NON_MEDICATION,
                flags=(Flag.HEADER_ARTEFACT,),
            )
        ]
    if column == "insulin_iv":
        return _parse_iv(norm, ctx, d, formulation_rules)
    lead, segs = _segments(norm, d)
    events: list[MedicationEvent] = []
    if _NOISE.sub("", _IU.sub(" ", _MASS.sub(" ", lead))):
        events.append(_unrecognised(ctx, lead.strip()))
    for entry, seg in segs:
        expected_misplaced = (
            column.startswith("csii")
            or (column == "insulin_sc" and entry.drug_class != "insulin")
            or (column == "oral_agents" and entry.drug_class == "insulin")
        )
        flags = [Flag.MISPLACED_COLUMN] if expected_misplaced else []
        if entry.canonical.startswith("COMBINATION:"):
            events += _combination(ctx, seg, entry, d, flags, formulation_rules)
            continue
        pattern = _IU if entry.dose_unit == "IU" else _MASS
        found = pattern.findall(seg)
        if _residue(seg, entry.alias, [pattern]):
            flags.append(Flag.UNRECOGNISED_TEXT)
        dose, unit = None, None
        if len(found) == 1:
            if entry.dose_unit == "IU":
                dose, unit = float(found[0]), "IU"
            else:
                value, u = found[0]
                dose, unit = round(float(value) * _TO_MG[u], 6), "mg"
        elif len(found) > 1:
            flags.append(Flag.MULTIPLE_DOSE_CANDIDATES)
        else:
            flags.append(Flag.DOSE_UNKNOWN)
            if re.search(_NUM, seg.replace(entry.alias, " ")):
                flags.append(Flag.UNIT_MISSING)
        events.append(
            _from_entry(ctx, seg.strip(" ,"), entry, dose, unit, flags, formulation_rules)
        )
    if not events:
        events.append(_unrecognised(ctx, norm))
    return events


def _combination(
    ctx: Context,
    seg: str,
    entry: DrugEntry,
    d: DrugDictionary,
    flags: list[Flag],
    rules: dict[str, Any],
) -> list[MedicationEvent]:
    comps = entry.components
    amounts = _MASS.findall(seg)
    out = []
    for k, comp in enumerate(comps):
        ce = d.by_canonical(comp)
        f = [*flags, Flag.COMBINATION_PRODUCT]
        dose = None
        if len(amounts) == len(comps):
            dose = round(float(amounts[k][0]) * _TO_MG[amounts[k][1]], 6)
        else:
            f.append(Flag.DOSE_UNKNOWN if not amounts else Flag.MULTIPLE_DOSE_CANDIDATES)
        out.append(
            _from_entry(
                ctx, seg.strip(" ,"), ce, dose, "mg" if dose is not None else None, f, rules
            )
        )
    return out


def _parse_iv(
    norm: str, ctx: Context, d: DrugDictionary, rules: dict[str, Any]
) -> list[MedicationEvent]:
    events = []
    for comp in [c.strip() for c in norm.split(",") if c.strip()]:
        _, segs = _segments(comp, d)
        if len(segs) != 1:
            events.append(_unrecognised(ctx, comp))
            continue
        entry, _ = segs[0]
        if entry.drug_class == "insulin":
            doses = _IU.findall(comp)
            flags = [Flag.RATE_UNKNOWN]
            dose = float(doses[0]) if len(doses) == 1 else None
            if len(doses) != 1:
                flags.append(Flag.DOSE_UNKNOWN if not doses else Flag.MULTIPLE_DOSE_CANDIDATES)
            ev = _from_entry(
                ctx, comp, entry, dose, "IU" if dose is not None else None, flags, rules, route="iv"
            )
            events.append(replace(ev, exposure_family="insulin_iv_flag", kernel_components=None))
            continue
        vol, pct = _ML.findall(comp), _PCT.findall(comp)
        flags = [Flag.GLUCOSE_INFUSION] if entry.drug_class == "iv_glucose" else []
        if len(vol) != 1:
            flags.append(Flag.DOSE_UNKNOWN)
        events.append(
            _base(
                ctx,
                comp,
                EventKind.IV_FLUID,
                ParseStatus.NON_TARGET_MEDICATION,
                canonical=entry.canonical,
                drug_class=entry.drug_class,
                subclass=entry.subclass,
                route="iv",
                formulation=entry.formulation,
                formulation_basis="DICTIONARY",
                dose=float(vol[0]) if len(vol) == 1 else None,
                dose_unit="ml",
                concentration_pct=float(pct[0]) if len(pct) == 1 else None,
                exposure_family=entry.exposure_family,
                flags=tuple(flags),
            )
        )
    return events or [_unrecognised(ctx, norm)]


def parse_cell(
    value: object, column: str, ctx: Context, d: DrugDictionary, formulation_rules: dict[str, Any]
) -> EntryParse:
    """Parse one raw medication cell. Numbers are valid only in the CSII columns."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        v = float(value)
        if column == "csii_bolus":
            e = d.lookup("novolin r")  # column header: CSII - bolus insulin (Novolin R, IU)
            events = [_from_entry(ctx, str(value), e, v, "IU", [], formulation_rules, route="csii")]
        elif column == "csii_basal":
            flags = (Flag.ZERO_DOSE,) if v == 0 else ()
            status = ParseStatus.PARSED_WITH_WARNING if flags else ParseStatus.PARSED
            if not 0 <= v <= 5:
                flags, status = (*flags, Flag.DOSE_IMPLAUSIBLE), ParseStatus.PARSED_WITH_WARNING
            events = [
                _base(
                    ctx,
                    str(value),
                    EventKind.PUMP_BASAL_RATE,
                    status,
                    canonical="regular_human_insulin",
                    drug_class="insulin",
                    subclass="short_human",
                    route="csii",
                    formulation="solution",
                    formulation_basis="DICTIONARY",
                    dose=v,
                    dose_unit="IU/h",
                    target=True,
                    exposure_family="insulin_regular",
                    kernel_components="regular_human:1.0",
                    flags=flags,
                )
            ]
        else:
            events = [_unrecognised(ctx, str(value))]
        return EntryParse(raw_text=str(value), source_column=column, events=tuple(events))
    text = str(value)
    return EntryParse(
        raw_text=text,
        source_column=column,
        events=tuple(parse_text(text, column, ctx, d, formulation_rules)),
    )
