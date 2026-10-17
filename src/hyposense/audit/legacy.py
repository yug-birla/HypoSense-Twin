"""Legacy (blueprint-audit) definitions, used ONLY to reproduce and reconcile the blueprint's
reported numbers. NOT production logic. The production treated-status definition comes from the
S3 medication parser and replaces `legacy_treatment` for every scientific use.

Transcribed from HypoSense_v2_sources/audit_scripts/audit.py (lines 35-70, 112-125, 140-149).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from hyposense.data.records import Recording
from hyposense.labels.eligibility import PredictionLabels

LEGACY_INSULIN = [  # (regex, class) — audit.py INSULIN, order matters (first match wins)
    (r"aspart\s*(70/30|50/50|30)|novomix", "premix_analogue"),
    (r"lispro\s*(25|50)|humalog\s*mix", "premix_analogue"),
    (r"30r|70/30|40r|50r|mix", "premix_human"),
    (r"glargine|glarigine|detemir|degludec|lantus|levemir|tresiba", "basal_analogue"),
    (r"novolin n|humulin n|nph|isophane", "intermediate_nph"),
    (r"aspart|glulisine|lispro|novorapid|apidra|humalog", "rapid_analogue"),
    (r"novolin r|gansulin r|humulin r|regular", "short_human"),
]
LEGACY_ORAL = {  # audit.py ORAL, insertion order matters
    "sulfonylurea": r"gliclazide|glimepiride|glibenclamide|glyburide|glipizide|gliquidone",
    "glinide": r"repaglinide|nateglinide|mitiglinide",
    "metformin": r"metformin",
    "agi": r"acarbose|voglibose|miglitol",
    "dpp4": r"gliptin",
    "sglt2": r"gliflozin",
    "tzd": r"glitazone",
    "glp1": r"glutide|exenatide|loxenatide",
}
IV_INSULIN_RE = re.compile(r"novolin|humulin|gansulin|insulin")


@dataclass(frozen=True)
class LegacyTreatment:
    insulin_any: bool  # legacy: any matched s.c. insulin class, or any CSII cell, or any i.v. cell
    secretagogue_any: bool  # any oral component classified sulfonylurea or glinide
    insulin_strict: bool  # variant: i.v. cells count only if they name an insulin (diagnostic)
    iv_only_insulin: bool  # legacy insulin_any is true ONLY because of i.v. cells


def _ins_classes(text: str) -> list[str]:
    out = []
    for part in re.split(r",\s*(?=[a-z])", text.lower()):
        cls = next((c for rx, c in LEGACY_INSULIN if re.search(rx, part)), None)
        if cls:
            out.append(cls)
    return out


def _oral_classes(text: str) -> list[str]:
    out = []
    for part in text.lower().split(","):
        cls = next((c for c, rx in LEGACY_ORAL.items() if re.search(rx, part)), None)
        if cls:
            out.append(cls)
    return out


def legacy_treatment(rec: Recording) -> LegacyTreatment:
    f = rec.frame
    sc = any(_ins_classes(str(v)) for v in f["insulin_sc"].dropna())
    csii = bool(
        (
            f["csii_bolus"].notna()
            | f["raw_csii_bolus"].notna()
            | f["csii_basal"].notna()
            | f["raw_csii_basal"].notna()
        ).any()
    )
    iv_cells = [str(v) for v in f["insulin_iv"].dropna()]
    iv_any = len(iv_cells) > 0
    iv_insulin = any(IV_INSULIN_RE.search(v.lower()) for v in iv_cells)
    secretagogue = any(
        c in ("sulfonylurea", "glinide")
        for v in f["oral_agents"].dropna()
        for c in _oral_classes(str(v))
    )
    insulin_any = sc or csii or iv_any
    return LegacyTreatment(
        insulin_any=insulin_any,
        secretagogue_any=secretagogue,
        insulin_strict=sc or csii or iv_insulin,
        iv_only_insulin=insulin_any and not (sc or csii),
    )


def legacy_warnable(
    labels: PredictionLabels, onsets: npt.NDArray[np.int64], horizon_s: int
) -> npt.NDArray[np.bool_]:
    """audit.py: an onset is 'warnable' if it is the FIRST onset after some eligible positive t
    (no 15-min minimum lead). Reconciliation only; production uses eligibility.warnable_onsets."""
    hit: set[int] = set()
    for t, e in zip(labels.ts.tolist(), labels.eligible.tolist(), strict=True):
        if not e:
            continue
        nxt = onsets[(onsets > t) & (onsets <= t + horizon_s)]
        if len(nxt):
            hit.add(int(nxt[0]))
    return np.array([int(o) in hit for o in onsets.tolist()], dtype=bool)
