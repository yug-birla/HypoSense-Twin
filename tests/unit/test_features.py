"""Feature-builder tests (S4): exact window boundaries, M0 equivalence with the executable spec,
missingness semantics, medication assembly and the feature-specification contracts.
All data SYNTHETIC."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from hyposense.features.cgm import ls_slope
from hyposense.features.medication import CATEGORY_CLASS
from hyposense.features.snapshot import LEVEL_INDEX, FeatureInputs
from hyposense.features.spec import (
    BY_NAME,
    FEATURES,
    LEVELS,
    UNION_NAMES,
    FeatureSpecMismatch,
    Group,
    Missing,
    check_names,
    level_names,
    spec_document,
    spec_sha256,
)
from hyposense.medication.exposure import QualityState
from tests.unit.state_helpers import (
    BUILDER,
    CFG,
    T0,
    cgm,
    context,
    meal,
    med,
    run,
    steady,
)

REPO = Path(__file__).resolve().parents[2]


def feats(events, ctx=None) -> dict[str, float]:  # type: ignore[no-untyped-def]
    s = run(events, ctx)[-1]
    return BUILDER.union_dict(FeatureInputs.of(s))


# ---------------------------------------------------------------- G1 / G2
def test_ls_slope_matches_numpy_polyfit() -> None:
    rng = np.random.default_rng(0)
    for _ in range(200):
        n = int(rng.integers(3, 12))
        ts = np.sort(rng.choice(np.arange(0, 7200, 60), n, replace=False)).astype(np.int64)
        g = rng.uniform(40, 300, n)
        ref = np.polyfit((ts - ts[-1]) / 60, g, 1)[0]
        assert ls_slope(ts, g) == pytest.approx(ref, rel=1e-9, abs=1e-12)


def test_m0_projection_is_the_executable_spec() -> None:
    # audit2.py: w = (ts > t - 35 min) & (ts <= t); >= 3 readings; proj = g(t) + slope * 60
    f = feats(cgm([(0, 150.0), (15, 140.0), (30, 120.0), (45, 110.0)]))
    ts = np.array([15, 30, 45]) * 60
    slope = np.polyfit((ts - ts[-1]) / 60, [140.0, 120.0, 110.0], 1)[0]
    assert f["cgm_slope30"] == pytest.approx(slope)
    assert f["cgm_m0_proj60"] == pytest.approx(110.0 + 60 * slope)
    assert f["cgm_m0_proj30"] == pytest.approx(110.0 + 30 * slope)


def test_trend_window_boundaries() -> None:
    # reading exactly 35 min before t is OUTSIDE (t - 35, t]; 34 min before is inside
    out = feats(cgm([(0, 100.0), (20, 100.0), (35, 100.0)]))
    assert math.isnan(out["cgm_slope30"]) and out["cgm_slope30_missing"] == 1.0
    assert math.isnan(out["cgm_m0_proj60"]) and math.isnan(out["cgm_accel"])
    inside = feats(cgm([(1, 100.0), (20, 100.0), (35, 100.0)]))
    assert inside["cgm_slope30"] == 0.0 and inside["cgm_slope30_missing"] == 0.0


def test_lags_nearest_within_tolerance_ties_earlier() -> None:
    f = feats(cgm([(0, 90.0), (8, 95.0), (38, 101.0), (52, 105.0), (60, 110.0)]))
    # t = 60: lag15 target 45 -> 38 (7 away) and 52 (7 away): tie -> earlier (101)
    assert f["cgm_lag15"] == 101.0
    assert f["cgm_lag60"] == 90.0  # target 0, exact
    assert f["cgm_lag45"] == 95.0  # target 15 -> 8 (7 away)
    assert math.isnan(f["cgm_lag30"]) and f["cgm_lag30_missing"] == 1.0  # target 30: 38 is 8 away
    g = feats(cgm([(0, 90.0), (37, 101.0), (60, 110.0)]))
    assert math.isnan(g["cgm_lag15"])  # 8 min from the target: outside +/- 7.5


def test_consecutive_falling_count_breaks_on_gap_and_ties() -> None:
    f = feats(cgm([(0, 150.0), (15, 140.0), (30, 140.0), (45, 130.0), (60, 120.0), (75, 110.0)]))
    assert f["cgm_n_falling"] == 3.0  # 140 = 140 breaks the run
    g = feats(cgm([(0, 150.0), (15, 140.0), (40, 130.0), (55, 120.0)]))
    assert g["cgm_n_falling"] == 1.0  # the 25-min step (> 20) breaks the run


# ---------------------------------------------------------------- G3 / G4
def test_statistics_windows_are_half_open() -> None:
    # t = 240; the 2-h window (120, 240] excludes the reading at exactly 120
    pts = [(m, 200.0 if m == 120 else 100.0 + m / 15) for m in range(0, 241, 15)]
    f = feats(cgm(pts))
    win = [100.0 + m / 15 for m in range(135, 241, 15)]
    assert f["cgm_mean_2h"] == pytest.approx(np.mean(win))
    assert f["cgm_sd_2h"] == pytest.approx(np.std(win, ddof=1))
    assert f["cgm_min_2h"] == min(win)
    assert f["cgm_mean_6h"] == pytest.approx(np.mean([v for _, v in pts]))
    assert f["cgm_cv_24h"] == pytest.approx(f["cgm_sd_24h"] / f["cgm_mean_24h"])


def test_history_features() -> None:
    pts = [*steady(0, 100, 120.0), (105, 66.6), (120, 64.8), *steady(135, 1440 + 135, 79.2)]
    f = feats(cgm(pts))
    assert f["cgm_prior_l1_onsets"] == 1.0
    assert f["cgm_min_since_low70"] == 1440.0  # capped
    assert f["cgm_min_below80_24h"] == 15.0 * 96  # every reading in (t - 24 h, t] is 79.2
    assert f["sensor_day"] == 2.0 and not math.isnan(f["cgm_pct_own"])
    young = feats(cgm(steady(0, 600, 120.0)))
    assert math.isnan(young["cgm_min_since_low70"]) and young["cgm_min_since_low70_missing"] == 1
    assert math.isnan(young["cgm_pct_own"]) and young["cgm_pct_own_missing"] == 1
    assert young["sensor_day"] == 1.0


def test_own_percentile_is_mid_rank() -> None:
    pts = [(m, 100.0) for m in range(0, 1441, 15)] + [(1455, 100.0)]
    f = feats(cgm(pts))
    assert f["cgm_pct_own"] == 50.0  # all equal -> mid-rank 50
    pts2 = [(m, 50.0 + m) for m in range(0, 1441, 15)]
    assert feats(cgm(pts2))["cgm_pct_own"] == pytest.approx(100 * (96 + 0.5) / 97)


def test_time_features_use_the_local_clock() -> None:
    # T0 is 20:40 local. 3h20 later = 00:00 (night), 9h20 later = 06:00 (not night)
    midnight = feats(cgm([(200, 100.0)]))
    assert midnight["night"] == 1.0 and midnight["hour_sin"] == pytest.approx(0.0, abs=1e-12)
    assert midnight["hour_cos"] == pytest.approx(1.0)
    assert feats(cgm([(559, 100.0)]))["night"] == 1.0  # 05:59
    assert feats(cgm([(560, 100.0)]))["night"] == 0.0  # 06:00


# ---------------------------------------------------------------- G5 / G6
def test_static_features_and_indicators() -> None:
    f = feats(cgm([(0, 100.0)]))
    assert f["age_y"] == 60 and f["sex_male"] == 1 and f["weight_kg"] == 70
    assert math.isnan(f["egfr"]) and f["egfr_missing"] == 1 and f["age_y_missing"] == 0
    assert f["rx_premix"] == 1 and f["rx_su"] == 1 and f["rx_missing"] == 0
    g = feats(cgm([(0, 100.0)]), context(regimen=None))
    assert all(math.isnan(g[k]) for k in g if k.startswith("rx_") and k != "rx_missing")
    assert g["rx_missing"] == 1


def test_meal_features() -> None:
    f = feats([*cgm([(0, 100.0), (180, 100.0)]), meal(0), meal(30, known=False)])
    assert f["meal_min_since"] == 150.0 and f["meal_last_3h"] == 1.0
    assert f["meal_last_content_unknown"] == 1.0 and f["meal_none_logged"] == 0
    edge = feats([*cgm([(180, 100.0)]), meal(0)])
    assert edge["meal_last_3h"] == 0.0  # exactly 180 min ago is outside (t - 180, t]
    cap = feats([*cgm([(800, 100.0)]), meal(0)])
    assert cap["meal_min_since"] == 720.0
    none = feats(cgm([(0, 100.0)]))
    assert math.isnan(none["meal_min_since"]) and none["meal_none_logged"] == 1
    assert math.isnan(none["meal_last_content_unknown"]) and none["meals_today"] == 0


def test_meals_today_counts_from_local_midnight() -> None:
    # T0 = 20:40 local; meals at 21:00 (day 1) and 00:20 (day 2); t = 01:00 (day 2)
    f = feats([*cgm([(260, 100.0)]), meal(20), meal(220)])
    assert f["meals_today"] == 1.0


# ---------------------------------------------------------------- G7 / G78 / G8
def test_medication_groups_reuse_the_s3_engine() -> None:
    from hyposense.state.medication import MedicationExposureState

    events = [
        *cgm(steady(0, 240)),
        *med("insulin aspart 70/30 10 IU", "insulin_sc", 30),
        *med("insulin aspart 70/30 6 IU", "insulin_sc", 60),
        *med("gliclazide 30 mg", "oral_agents", 30),
    ]
    s = run(events)[-1]
    f = BUILDER.union_dict(FeatureInputs.of(s))
    eng = s.medication.engine().compute(np.array([s.ts], dtype=np.int64))
    for k in ("act_insulin_total", "iob_insulin", "insulin_p60", "act_su", "min_since_insulin"):
        assert f[k] == eng[k][0]
    assert f["delta_insulin_60"] == f["insulin_p60"] - f["act_insulin_total"]
    assert f["act_insulin_total_per_kg"] == f["act_insulin_total"] / 70.0
    assert f["insulin_bolus_n_24h"] == 2 and f["insulin_bolus_dose_24h"] == 16.0
    assert f["insulin_bolus_last_dose"] == 6.0 and f["insulin_bolus_min_since_last"] == 180.0
    assert f["quality_insulin"] == list(QualityState).index(QualityState.KNOWN)
    assert isinstance(s.medication, MedicationExposureState)


def test_timing_unknown_masks_raw_timing_but_not_counts() -> None:
    # SU prescribed (context regimen) but never logged -> TIMING_UNKNOWN for the SU class
    f = feats([*cgm(steady(0, 240)), *med("insulin aspart 70/30 10 IU", "insulin_sc", 30)])
    assert f["quality_sulfonylurea"] == list(QualityState).index(QualityState.TIMING_UNKNOWN)
    assert math.isnan(f["su_min_since_last"]) and math.isnan(f["su_dose_24h"])
    assert f["su_n_24h"] == 0.0 and f["su_missing"] == 1.0
    assert math.isnan(f["act_su"]) and math.isnan(f["delta_su_60"])
    # glinide neither prescribed nor logged: a true zero exposure, NaN min-since (never logged)
    assert f["act_glinide"] == 0.0 and f["quality_glinide"] == 5.0
    assert math.isnan(f["min_since_glinide"]) and f["min_since_glinide_missing"] == 1.0
    assert f["glinide_dose_24h"] == 0.0 and f["glinide_missing"] == 1.0


def test_per_kg_needs_known_weight() -> None:
    f = feats(
        [*cgm(steady(0, 120)), *med("insulin aspart 70/30 10 IU", "insulin_sc", 30)],
        context(weight=float("nan")),
    )
    assert math.isnan(f["act_insulin_total_per_kg"]) and f["weight_kg_missing"] == 1
    assert f["act_insulin_total"] > 0


def test_category_class_mapping_is_the_contract() -> None:
    assert CATEGORY_CLASS == {
        "insulin_bolus": "insulin",
        "insulin_basal": "insulin",
        "su": "sulfonylurea",
        "glinide": "glinide",
    }


# ---------------------------------------------------------------- specification contracts
def test_union_matches_specification_exactly() -> None:
    f = feats([*cgm(steady(0, 1500)), meal(100), *med("gliclazide 30 mg", "oral_agents", 90)])
    assert set(f) == set(UNION_NAMES) and len(UNION_NAMES) == len(set(UNION_NAMES))


def test_level_membership() -> None:
    m1, m2, m3r, m3 = (set(level_names(lvl)) for lvl in LEVELS)
    g = {grp: {f.name for f in FEATURES if f.group is grp} for grp in Group}
    assert m1 == g[Group.G1] | g[Group.G2] | g[Group.G3] | g[Group.G4]
    assert m2 == m1 | g[Group.G5] | g[Group.G6]
    assert m3r - m2 == g[Group.G7] | g[Group.G78] and m2 < m3r
    assert m3 - m2 == g[Group.G8] | g[Group.G78] and m2 < m3  # the single M2 -> M3 change
    assert not (g[Group.G7] & m3) and not (g[Group.G8] & m3r)
    assert [len(level_names(lvl)) for lvl in LEVELS] == [38, 72, 95, 100]


def test_every_indicator_is_in_the_same_level_as_its_features() -> None:
    for lvl in LEVELS:
        names = set(level_names(lvl))
        for n in names:
            f = BY_NAME[n]
            if f.missing is Missing.NAN_WITH_INDICATOR:
                assert f.indicators and set(f.indicators) <= names, (lvl, n)
            else:
                assert not f.indicators, n


def test_spec_records_are_complete_and_safe() -> None:
    for f in FEATURES:
        assert f.name and f.unit and f.source and f.computation and f.availability and f.ref
        assert f.causal and f.version == "1.0.0"
        assert "hypoglyc" not in f.name and "patient" not in f.name and f.name != "id"
    labs = {f.name for f in FEATURES if f.lab}
    assert labs == {"hba1c_mmol_mol", "egfr", "c_peptide_fasting_nmol_l"}


def test_feature_spec_mismatch_is_raised() -> None:
    names = list(level_names("M2"))
    check_names("M2", names)
    with pytest.raises(FeatureSpecMismatch):
        check_names("M2", names[::-1])
    with pytest.raises(FeatureSpecMismatch):
        check_names("M3", names)
    with pytest.raises(FeatureSpecMismatch):
        level_names("M9")


def test_committed_feature_spec_matches_the_registry() -> None:
    path = REPO / "artifacts" / "features" / "feature_spec.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    expected = spec_document(CFG["features"])
    assert doc["sha256"] == spec_sha256(CFG["features"])
    assert {k: v for k, v in doc.items() if k != "sha256"} == json.loads(json.dumps(expected))


def test_snapshot_is_a_selection_of_the_union() -> None:
    s = run([*cgm(steady(0, 300)), *med("gliclazide 30 mg", "oral_agents", 90)])[-1]
    union = BUILDER.union(FeatureInputs.of(s))
    for lvl in LEVELS:
        snap = BUILDER.snapshot(s, lvl)
        assert snap.names == level_names(lvl) and snap.ts == T0 + 300 * 60
        assert snap.values.tobytes() == union[LEVEL_INDEX[lvl]].tobytes()
        assert snap.spec_sha256 == BUILDER.spec_sha256 and len(snap.digest) == 64
