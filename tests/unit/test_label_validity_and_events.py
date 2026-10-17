"""Label validity, annotations, legacy treatment, event audit and G2/G3b tests (SYNTHETIC)."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest

from hyposense.audit.events import m_w, measure_events
from hyposense.audit.gates import evaluate_g2, evaluate_g3b, precision_table
from hyposense.audit.legacy import legacy_treatment
from hyposense.data.loader import load_recording
from hyposense.labels.annotations import annotate, floor_runs
from hyposense.labels.config import LabelConfig
from hyposense.labels.episodes import EndReason, Episode
from hyposense.labels.validity import (
    CBGSeries,
    agreement_stats,
    episode_cbg_status,
    episode_cbg_status_onset_window,
    pair_cbg_cgm,
)
from tests.conftest import WorkbookFactory, row

G3B = {"max_unconfirmed_share": 0.50, "pair_window_min": 8, "episode_cbg_tail_min": 15}
G2 = {
    "min_episodes": 100,
    "min_patients_with_episode": 20,
    "max_ci_half_width": 0.15,
    "icc_ref": 0.15,
    "p_ref": 0.65,
    "icc_grid": [0.05, 0.15, 0.30],
}


def _ep(onset: int, last: int, end: int | None, a: int = 0, b: int = 1) -> Episode:
    return Episode(
        "L1",
        a,
        b,
        onset,
        end,
        last,
        EndReason.RECOVERED if end else EndReason.RECORD_END,
        60.0,
        b - a,
    )


# ---------------- CBG pairing and confirmation ----------------


def test_pairing_nearest_within_window_ties_to_earlier() -> None:
    cgm_ts = np.array([0, 900, 1800], dtype=np.int64)
    cgm_v = np.array([60.0, 70.0, 80.0])
    cbg = CBGSeries(
        np.array([450, 1800 + 480, 1800 + 481, -100], dtype=np.int64),
        np.array([100.0, 90.0, 95.0, 50.0]),
    )
    b, g = pair_cbg_cgm(cbg, cgm_ts, cgm_v, 480)
    # 450 is equidistant to 0 and 900 -> earlier (60); 2280 pairs (dt=480); 2281 does not (481);
    # -100 pairs with 0 (dt=100)
    assert b.tolist() == [100.0, 90.0, 50.0]
    assert g.tolist() == [60.0, 80.0, 60.0]


def test_episode_confirmation_window_is_closed_and_tail_15min() -> None:
    ep = _ep(onset=1000, last=2000, end=2900)
    cbg = CBGSeries(
        np.array([999, 1000, 2900, 2901], dtype=np.int64), np.array([60.0, 90.0, 65.0, 40.0])
    )
    assert episode_cbg_status(ep, cbg, 900, 70.0) is True  # 2900 = last + 15 min, < 70
    cbg2 = CBGSeries(np.array([1000, 2900], dtype=np.int64), np.array([90.0, 85.0]))
    assert episode_cbg_status(ep, cbg2, 900, 70.0) is False
    cbg3 = CBGSeries(np.array([999, 2901], dtype=np.int64), np.array([50.0, 50.0]))
    assert episode_cbg_status(ep, cbg3, 900, 70.0) is None  # outside window: no status
    assert (
        episode_cbg_status_onset_window(ep, CBGSeries(np.zeros(0, np.int64), np.zeros(0)), 70.0)
        is None
    )


def test_agreement_stats() -> None:
    s = agreement_stats(np.array([100.0, 60.0, 200.0]), np.array([90.0, 65.0, 180.0]))
    assert s["pairs"] == 3 and s["cgm_minus_cbg_mean"] == pytest.approx(-8.3, abs=0.05)
    assert s["pairs_cgm_lt70"] == 1 and s["pairs_cgm_lt70_cbg_lt70"] == 1
    assert s["mard_pct"] == pytest.approx(round((10 / 100 + 5 / 60 + 20 / 200) / 3 * 100, 1))


# ---------------- annotations ----------------


def test_floor_runs_require_8_consecutive_readings() -> None:
    ts = np.arange(0, 12 * 900, 900, dtype=np.int64)
    g = np.array([100, 39.6, 39.6, 39.6, 39.6, 39.6, 39.6, 39.6, 39.6, 100, 39.6, 39.6])
    assert floor_runs(ts, g) == [(1, 9)]
    g7 = g.copy()
    g7[8] = 41.0
    assert floor_runs(ts, g7) == []  # only 7 consecutive


def test_compression_candidate_and_nocturnal() -> None:
    # onset 02:00 local (+08:00) = 18:00 UTC; steep fall 100 -> 66 in 15 min; 30-min episode
    base = 18 * 3600
    ts = np.array([base - 900, base, base + 900, base + 1800, base + 2700], dtype=np.int64)
    g = np.array([100.0, 66.0, 64.0, 80.0, 82.0])
    ep = Episode("L1", 1, 3, int(ts[1]), int(ts[3]), int(ts[2]), EndReason.RECOVERED, 64.0, 2)
    a = annotate(ep, ts, g, 8 * 3600)
    assert a.nocturnal and a.compression_candidate and a.onset_local_hour == 2
    assert a.prior_reading_lt80 is False and a.within_first_24h is True


# ---------------- legacy treatment ----------------

T0 = datetime(2021, 3, 1, 8, 0)


def _rec(make_workbook: WorkbookFactory, name: str, **cells: object):  # type: ignore[no-untyped-def]
    rows = [
        row(T0 + timedelta(minutes=15 * k), 100.0, **(cells if k == 1 else {})) for k in range(20)
    ]
    return load_recording(make_workbook(name, rows))


@pytest.mark.parametrize(
    ("cells", "insulin", "secretagogue", "iv_only"),
    [
        ({"insulin_sc": "Novolin 30R 8 IU"}, True, False, False),
        ({"insulin_sc": "scilin m30 8 IU"}, False, False, False),  # legacy regex misses it (S3 fix)
        ({"oral": "gliclazide 30 mg, metformin 500 mg"}, False, True, False),
        ({"oral": "metformin 500 mg"}, False, False, False),
        ({"csii_basal": "temporarily suspend insulin delivery"}, True, False, False),
        ({"iv": "10% potassium chloride 10 ml"}, True, False, True),  # legacy counts any i.v. cell
    ],
)
def test_legacy_treatment(
    make_workbook: WorkbookFactory,
    cells: dict[str, object],
    insulin: bool,
    secretagogue: bool,
    iv_only: bool,
) -> None:
    t = legacy_treatment(_rec(make_workbook, "2001_0_20210301.xlsx", **cells))
    assert (t.insulin_any, t.secretagogue_any, t.iv_only_insulin) == (
        insulin,
        secretagogue,
        iv_only,
    )
    if iv_only:
        assert t.insulin_strict is False


# ---------------- event audit on synthetic recordings ----------------


def test_measure_events_populates_every_section(make_workbook: WorkbookFactory) -> None:
    spec = [100.0] * 13 + [66.0, 64.0, 80.0, 82.0] + [100.0] * 10
    rows = [
        row(
            T0 + timedelta(minutes=15 * k),
            v,
            insulin_sc="Novolin R 4 IU" if k == 2 else None,
            cbg=60.0 if k == 14 else None,
        )
        for k, v in enumerate(spec)
    ]
    rec = load_recording(make_workbook("2001_0_20210301.xlsx", rows))
    m = measure_events([rec], LabelConfig(), 8 * 3600, {"2001": "T"}, G3B)
    l1 = m["episodes"]["L1"]
    assert l1["episodes"] == 1 and l1["end_reasons"] == {"recovered": 1}
    assert l1["duration_min_q1_median_q3"] == [30.0, 30.0, 30.0] and l1["nadir_median"] == 64.0
    assert m["prediction_times"]["positive"] == 4  # onset at 195 min: t = 135..180
    assert m["by_partition"]["T"]["treated_L1"] == 1
    assert m["label_validity"]["L1_cbg_during_confirmed"] == 1
    bd = m["blueprint_definitions"]
    assert bd["L1_end_reason"] == {"recovered": 1} and bd["L1_duration_min_median"] == 30.0


def test_m_w() -> None:
    assert m_w([2, 2]) == 2.0 and m_w([4, 0]) == 4.0 and m_w([]) is None


# ---------------- gates ----------------


def test_precision_table_reproduces_blueprint_table_8_4() -> None:
    rows = {r["icc"]: r for r in precision_table(154, 9.23, 0.65, [0.05, 0.15, 0.30])}
    assert (rows[0.05]["design_effect"], round(rows[0.05]["effective_n"])) == (1.41, 109)
    assert (rows[0.15]["design_effect"], round(rows[0.15]["effective_n"])) == (2.23, 69)
    assert rows[0.15]["ci_half_width"] == pytest.approx(0.113, abs=0.0005)
    assert rows[0.30]["ci_half_width"] == pytest.approx(0.140, abs=0.0015)
    assert (
        round(rows[0.05]["mdd_discordance_15"], 2),
        round(rows[0.05]["mdd_discordance_25"], 2),
    ) == (0.10, 0.13)
    assert (
        round(rows[0.30]["mdd_discordance_15"], 2),
        round(rows[0.30]["mdd_discordance_25"], 2),
    ) == (0.16, 0.21)


@pytest.mark.parametrize(
    ("eps", "pts", "mw", "status"),
    [
        (154, 30, 9.23, "PASS"),
        (99, 30, 2.0, "FAIL"),
        (154, 19, 9.23, "FAIL"),
        (100, 20, 40.0, "FAIL"),  # precision fails
    ],
)
def test_g2(eps: int, pts: int, mw: float, status: str) -> None:
    g = evaluate_g2(
        measured={"E_treated_L1": eps, "E_treated_with_L1": pts, "E_treated_m_w": mw},
        criteria=G2,
        provisional_reasons=["x"],
    )
    assert g["status"] == status and g["conditions"] == ["x"]


@pytest.mark.parametrize(
    ("with_cbg", "confirmed", "status"),
    [(65, 11, "TRIGGERED"), (10, 5, "PASS"), (10, 4, "TRIGGERED"), (0, 0, "FAIL")],
)
def test_g3b(with_cbg: int, confirmed: int, status: str) -> None:
    g = evaluate_g3b(
        measured={"L1_with_cbg_during": with_cbg, "L1_cbg_during_confirmed": confirmed},
        criteria=G3B,
    )
    assert g["status"] == status
    assert bool(g["consequences_applied"]) == (status == "TRIGGERED")
