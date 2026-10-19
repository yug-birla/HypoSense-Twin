"""Confirmatory report generator (S10): results tables, model card and figures, written ONLY
from a `hyposense confirm` results document via `reporting.confirm_view`. It computes no metric;
every number is copied from the frozen document, and the document's status heads every output.

Official: `hyposense report` (after `freeze.verify_confirmation`) writes docs/results/.
Rehearsal: `hyposense report --rehearsal RUN` writes experiments/runs/RUN/report/, and every
file is stamped REHEARSAL (development; never evidence).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.reporting.confirm_view import LADDER, confirmatory_view

RUNS = REPO_ROOT / "experiments" / "runs"
OFFICIAL_OUT = REPO_ROOT / "docs" / "results"


def _pct(v: float | None, d: int = 1) -> str:
    return "—" if v is None else f"{100 * v:.{d}f} %"


def _pp(v: float | None) -> str:
    return "—" if v is None else f"{100 * v:+.1f} pp"


def _ci_pp(ci: list[float] | None) -> str:
    return "—" if not ci else f"{_pp(ci[0])} to {_pp(ci[1])}"


def _num(v: float | None, d: int = 4) -> str:
    return "—" if v is None else f"{v:.{d}f}"


def _banner(v: dict[str, Any]) -> str:
    if v["status"] == "CONFIRMATORY":
        return (
            "> **Status: CONFIRMATORY.** Generated from the single official run on the sealed "
            "evaluation partition (E). Numbers are copied from the frozen results document."
        )
    return (
        f"> **Status: {v['status']}.** Generated from a T-only rehearsal of the confirmatory "
        "code. These are NOT confirmatory results and must not be cited as evidence."
    )


# ---------------------------------------------------------------- figures (plain SVG)
def forest_svg(v: dict[str, Any]) -> str:
    rows = [r for r in v["analyses"] if r["available"] and r.get("delta_ci95")]
    w, left, right, top, rh = 760, 300, 40, 44, 20
    h = top + rh * len(rows) + 40
    lo = float(min(-0.2, *(r["delta_ci95"][0] for r in rows)))
    hi = float(max(0.2, *(r["delta_ci95"][1] for r in rows)))

    def x(val: float) -> float:
        return left + (val - lo) / (hi - lo) * (w - left - right)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="11">',
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
        f'<text x="12" y="18" font-size="13" font-weight="bold">Δ sensitivity @ 1 FA/day, M3 - M2'
        f" (95 % paired patient-cluster bootstrap CI) — {escape(v['status'])}</text>",
        f'<line x1="{x(0):.1f}" y1="{top - 8}" x2="{x(0):.1f}" y2="{h - 30}" stroke="#888" '
        'stroke-dasharray="3,3"/>',
    ]
    for i, r in enumerate(rows):
        y = top + i * rh + rh / 2
        a, b = r["delta_ci95"]
        bold = ' font-weight="bold"' if r["key"] == "primary" else ""
        out += [
            f'<text x="12" y="{y + 4:.1f}"{bold}>{escape(r["label"])}</text>',
            f'<line x1="{x(a):.1f}" y1="{y:.1f}" x2="{x(b):.1f}" y2="{y:.1f}" stroke="#0e6e6a" '
            'stroke-width="2"/>',
            f'<circle cx="{x(r["delta"]):.1f}" cy="{y:.1f}" r="3.5" fill="#0e6e6a"/>',
        ]
    for t in (lo, 0.0, hi):
        out.append(
            f'<text x="{x(t):.1f}" y="{h - 14}" text-anchor="middle">{100 * t:+.0f} pp</text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def ladder_svg(v: dict[str, Any]) -> str:
    ms = [m for m in LADDER if v["ladder"][m]["sens1"] is not None]
    w, h, left, top, bh = 560, 60 + 34 * len(ms), 70, 40, 18
    right = 60

    def x(val: float) -> float:
        return left + val * (w - left - right)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="11">',
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
        f'<text x="12" y="18" font-size="13" font-weight="bold">Sensitivity @ 1 FA/day by model,'
        f" treated patients (95 % CI) — {escape(v['status'])}</text>",
    ]
    for i, m in enumerate(ms):
        e = v["ladder"][m]
        y = top + i * 34
        out += [
            f'<text x="12" y="{y + 13}">{m}</text>',
            f'<rect x="{left}" y="{y}" width="{x(e["sens1"]) - left:.1f}" height="{bh}" '
            f'fill="{"#0e6e6a" if m == "M3" else "#9aa5b1"}"/>',
            f'<text x="{x(e["sens1"]) + 4:.1f}" y="{y + 13}">{_pct(e["sens1"])}</text>',
        ]
        if e["sens1_ci95"]:
            a, b = e["sens1_ci95"]
            out.append(
                f'<line x1="{x(a):.1f}" y1="{y + bh + 4}" x2="{x(b):.1f}" y2="{y + bh + 4}" '
                'stroke="#333" stroke-width="1.5"/>'
            )
    out.append("</svg>")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- markdown
def results_md(v: dict[str, Any]) -> str:
    p = v["primary"]
    lines = [
        "# Confirmatory results (S9)",
        "",
        _banner(v),
        "",
        f"- Run: `{v['run_id']}` · results SHA-256 `{v['results_sha256']}`",
        f"- Freeze record: `{(v.get('freeze') or {}).get('record_sha256', '—')}`",
        f"- Code commit: `{v.get('commit')}`",
        f"- Population: {json.dumps(v['population'])}",
        "",
        "## Primary endpoint (H1)",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| M2 sens@1FA | {_pct(p['M2_sens_at_1fa'])} |",
        f"| M3 sens@1FA | {_pct(p['M3_sens_at_1fa'])} |",
        f"| Δ M3 - M2 | {_pp(p['delta'])} |",
        f"| 95 % CI | {_ci_pp(p['delta_ci95'])} |",
        f"| Undefined resamples (G5) | {p['undefined_resamples']} "
        f"({'pass' if p['g5_pass'] else 'FAIL'}) |",
        f"| **H1 supported** (lower bound > 0) | **{'YES' if p['h1_supported'] else 'NO'}** |",
        "",
        "## Model selection (ANALYSIS_PLAN §6, applied mechanically)",
        "",
        f"Selected: **{v['selection']['selected']}**",
        "",
        *[f"- {s}" for s in v["selection"]["steps"]],
        "",
        "## Interpretation (Blueprint Table 20.4, mechanical)",
        "",
        *([f"- {s}" for s in v["interpretation"]] or ["- No row applies."]),
        "",
        "## Model ladder (primary population)",
        "",
        "| Model | sens@1FA | 95 % CI | Log-loss | Deployed sens | FA/day | Precision "
        "| Median lead |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in LADDER:
        e = v["ladder"][m]
        d = v["deployed_operating_point"].get(m, {})
        ci = e["sens1_ci95"]
        lines.append(
            f"| {m} | {_pct(e['sens1'])} | "
            f"{'—' if not ci else _pct(ci[0]) + ' to ' + _pct(ci[1])} | {_num(e['logloss'])} | "
            f"{_pct(d.get('sensitivity'))} | {_num(d.get('fa_per_day'), 2)} | "
            f"{_pct(d.get('alert_precision'))} | "
            f"{'—' if d.get('lead_median_min') is None else str(d['lead_median_min']) + ' min'} |"
        )
    lines += [
        "",
        "Deployed = fold-frozen τA applied to held-out patients (a different quantity from the "
        "sens@1FA operating curve).",
        "",
        "## Paired contrasts (sens@1FA)",
        "",
        "| Contrast | Δ | 95 % CI |",
        "|---|---|---|",
        *[f"| {k} | {_pp(c['point'])} | {_ci_pp(c['ci95'])} |" for k, c in v["contrasts"].items()],
        "",
        f"S2 (FA/day at matched sensitivity, M3 - M2): "
        f"{_num(v['s2_matched_sensitivity_fa_delta']['point'], 3)} "
        f"(95 % CI {_num(v['s2_matched_sensitivity_fa_delta']['ci95'][0], 3)} to "
        f"{_num(v['s2_matched_sensitivity_fa_delta']['ci95'][1], 3)})",
        "",
        "## Secondary, sensitivity and robustness analyses",
        "",
        "![forest](forest.svg)",
        "",
        "| Group | Analysis | Patients | Episodes | M2 | M3 | Δ | 95 % CI |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in v["analyses"]:
        if not r["available"]:
            lines.append(f"| {r['group']} | {r['label']} | not available | | | | | |")
            continue
        lines.append(
            f"| {r['group']} | {r['label']} | {r['patients']} | {r['episodes']} | "
            f"{_pct(r['M2_sens1'])} | {_pct(r['M3_sens1'])} | {_pp(r['delta'])} | "
            f"{_ci_pp(r['delta_ci95'])} |"
        )
    dc = v["demo_cases"]
    lines += [
        "",
        "R3 caveat (pre-registered, ANALYSIS_PLAN §5.7 item 26): the logistic-regression learner "
        "overfits patient-level prescription flags; a low R3 value is a property of that learner.",
        "",
        "## Demo cases (ANALYSIS_PLAN §5.7 item 30, pre-specified selection)",
        "",
        f"Candidates: {json.dumps(dc.get('candidates'))}; seed {dc.get('seed')}.",
        "",
        *[
            f"- {cat}: `{c['recording_key']}` at ts {c['event_ts']}"
            if c
            else f"- {cat}: none eligible (no substitute taken)"
            for cat, c in (dc.get("selected") or {}).items()
        ],
        "",
        "![ladder](ladder.svg)",
        "",
    ]
    return "\n".join(lines)


def _review_line() -> str:
    by = load_config("pharma.yaml").get("reviewed_by")
    if not by:
        return "**no completed clinical-pharmacist review** (docs/medication/PHARMACIST_REVIEW.md)."
    return f"reviewed by {by} (docs/medication/PHARMACIST_REVIEW.md)."


def model_card_md(v: dict[str, Any], doc: dict[str, Any]) -> str:
    cfg = load_config()
    fm = doc["results"]["final_model"]
    final = fm.get("final") or {}
    ev = cfg["event"]
    p = v["primary"]
    return "\n".join(
        [
            "# Model card — HypoSense Twin",
            "",
            _banner(v),
            "",
            "## Intended use",
            "",
            "- Research and decision-support **prototype**. It is NOT a medical device and does "
            "not diagnose, treat or recommend medication or insulin doses.",
            "- Output: the risk of a CGM-detected level-1 hypoglycaemia episode "
            f"(CGM < {ev['threshold_mgdl']} mg/dL) within {ev['horizon_min']} min, with a "
            f"minimum lead of {ev['min_lead_min']} min. The supported action is human review / "
            "capillary confirmation.",
            "- Out of scope: outpatient use, paediatrics, populations other than the source "
            "dataset, and any autonomous action.",
            "",
            "## Model",
            "",
            f"- Selected by the pre-specified rule: **{fm['selected']}**.",
            f"- Final artefact: `{final.get('directory', '—')}` "
            f"(version `{final.get('model_version', '—')}`), retrained on all patients with the "
            "S7 procedure. Its thresholds are τA "
            f"{_num(final.get('tau_alert'))} and τW {_num(final.get('tau_watch'))}.",
            "- Learner: LightGBM (S6 hyperparameters, frozen before freeze), seed "
            f"{cfg['model']['seed']}. Calibration: canonical floored isotonic.",
            "- Alert policy: separate deterministic module (WATCH / ALERT / LOW NOW / "
            "INSUFFICIENT DATA / SYSTEM ERROR), 1 false alert per patient-day budget.",
            "",
            "## Data",
            "",
            "- Source: public ShanghaiT2DM CGM dataset (100 patients with type 2 diabetes, 109 "
            "recordings). Patient-level partition: tuning T (30) and sealed evaluation E (70).",
            "- Medication exposure from documented pharmacological kernels (configs/pharma.yaml).",
            f"- Kernel review: {_review_line()}",
            "",
            "## Performance (held-out, treated patients)",
            "",
            f"- sens@1FA: M2 {_pct(p['M2_sens_at_1fa'])}, M3 {_pct(p['M3_sens_at_1fa'])}; "
            f"Δ {_pp(p['delta'])} (95 % CI {_ci_pp(p['delta_ci95'])}).",
            f"- H1 (medication exposure adds value): "
            f"**{'supported' if p['h1_supported'] else 'not supported'}**.",
            "- Full tables: RESULTS.md.",
            "",
            "## Limitations",
            "",
            "- Single dataset and single centre; no external validation.",
            "- CGM-detected labels, not capillary-confirmed; sensor artefacts are possible.",
            "- Medication records come from retrospective documentation; administration times may "
            "be imprecise (R1 jitter analysis).",
            "- Few events per patient; wide confidence intervals.",
            "- No prospective or clinical-outcome evaluation; no claim of clinical benefit.",
            "",
            f"Source document: `{v['run_id']}` (results SHA-256 `{v['results_sha256']}`).",
            "",
        ]
    )


def write_report(doc: dict[str, Any], out: Path) -> dict[str, str]:
    v = confirmatory_view(doc)
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "RESULTS.md": results_md(v),
        "MODEL_CARD.md": model_card_md(v, doc),
        "forest.svg": forest_svg(v),
        "ladder.svg": ladder_svg(v),
    }
    for name, text in files.items():
        (out / name).write_text(text, "utf-8", newline="\n")
    return {k: (out / k).as_posix() for k in files}


def run_report(rehearsal_run: str | None = None) -> dict[str, Any]:
    if rehearsal_run is None:
        from hyposense.freeze import verify_confirmation

        ver = verify_confirmation()
        run, out = ver.confirm_run, OFFICIAL_OUT
    else:
        run, out = rehearsal_run, RUNS / rehearsal_run / "report"
    doc = json.loads((RUNS / run / "results.json").read_text("utf-8"))
    if rehearsal_run is not None and not str(doc["status"]).startswith("REHEARSAL"):
        raise ValueError(f"{rehearsal_run} is not a rehearsal run")
    return {"run": run, "status": doc["status"], "files": write_report(doc, out)}
