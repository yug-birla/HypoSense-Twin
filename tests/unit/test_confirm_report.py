"""S10 report generator: SYNTHETIC results document; every output carries the document status
and copies (never computes) its numbers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hyposense.reporting.confirm_report import write_report


def _iv(x: float) -> dict[str, Any]:
    return {"point": x, "ci95": [x - 0.1, x + 0.1], "undefined_resamples": 0}


def _doc(status: str) -> dict[str, Any]:
    ev = {
        "intervals": {"M2:sens1": _iv(0.8), "M3:sens1": _iv(0.9), "M3:logloss": _iv(0.03)},
        "comparisons": {"preview_M3-M2:sens1": _iv(0.1234)},
        "patients": 3,
        "episodes": 9,
    }
    return {
        "run_id": "SYNTHETIC-RUN",
        "results_sha256": "f" * 64,
        "results": {
            "status": status,
            "population": {"evaluation_patients": 3},
            "primary": {
                "M2_sens_at_1fa": 0.8,
                "M3_sens_at_1fa": 0.9,
                "delta": 0.1234,
                "delta_ci95": [0.0234, 0.2234],
                "undefined_resamples": 0,
                "g5_pass": True,
                "h1_supported": True,
            },
            "evaluations": {"primary": ev},
            "S2_matched_sensitivity_fa_delta": _iv(-0.2),
            "model_selection": {"selected": "M3", "steps": ["H1 supported -> M3"]},
            "interpretation_table_20_4": ["Δ CI > 0; M3 ≈ M3r"],
            "deployed_operating_point": {"M3": {"sensitivity": 0.85, "lead_min": {"median": 30}}},
            "final_model": {"selected": "M3", "final": {"directory": "x", "tau_alert": 0.1}},
            "demo_cases": {"seed": 2026, "candidates": {"TP": 1}, "selected": {"TP": None}},
        },
    }


def test_rehearsal_report_is_stamped_and_copies_numbers(tmp_path: Path) -> None:
    files = write_report(_doc("REHEARSAL (development; never evidence)"), tmp_path)
    assert set(files) == {"RESULTS.md", "MODEL_CARD.md", "forest.svg", "ladder.svg"}
    for name in files:
        text = (tmp_path / name).read_text("utf-8")
        assert "REHEARSAL" in text
    res = (tmp_path / "RESULTS.md").read_text("utf-8")
    assert "+12.3 pp" in res and "+2.3 pp to +22.3 pp" in res and "**YES**" in res
    assert "TP: none eligible (no substitute taken)" in res
    assert "not available" in res  # analyses absent from the document are shown as absent
    card = (tmp_path / "MODEL_CARD.md").read_text("utf-8")
    assert "NOT a medical device" in card and "NOT confirmatory" in card


def test_official_report_banner(tmp_path: Path) -> None:
    write_report(_doc("CONFIRMATORY"), tmp_path)
    res = (tmp_path / "RESULTS.md").read_text("utf-8")
    assert "Status: CONFIRMATORY." in res and "NOT confirmatory" not in res
