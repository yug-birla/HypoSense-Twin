"""Hand-labelled SYNTHETIC fixtures for the label builder (Blueprint Table 5.1; ANALYSIS_PLAN §0).

Every expected value was derived by hand from the written rules BEFORE the implementation
existed (test-first, CLAUDE.md §23). Times are minutes from recording start; values are mg/dL.
Expected episodes are (onset_min, end_min | None, end_reason, nadir, n_readings), where end_min is
the time of the reading that ends the episode (first confirmed recovery reading, or first reading
after a >30-min gap) and None means the episode runs to the record end.

Rules applied (L1 shown; L2 identical with 54 mg/dL):
- low   := value < 70 (70.0 is NOT low).
- onset := first reading i with low(i), low(i+1) and t(i+1) - t(i) <= 20 min.
- end   := scanning j = i+1, i+2, ...: if t(j) - t(j-1) > 30 min -> GAP at j; elif value(j) >= 70
           and value(j+1) >= 70 and t(j+1) - t(j) <= 20 min -> RECOVERED at j;
           record end -> RECORD_END.
- eligible t := value >= 70; not inside an L1 episode [onset, end); not in [end, end + 60 min);
           t - first reading >= 120 min; >= 7 readings in (t - 120 min, t];
           last reading - t >= 60 min OR an L1 onset in (t, t + 60 min].
- y(t) = 1 iff an L1 onset lies in (t, t + 60 min].
"""

from __future__ import annotations

from dataclasses import dataclass, field

R, G, E = "recovered", "gap", "record_end"
Ep = tuple[int, int | None, str, float, int]


def steady(start: int, stop: int, value: float = 100.0, step: int = 15) -> list[tuple[int, float]]:
    return [(m, value) for m in range(start, stop + 1, step)]


@dataclass(frozen=True)
class Fixture:
    name: str
    covers: str
    readings: list[tuple[int, float]]
    l1: list[Ep]
    l2: list[Ep] | None = None
    single: list[Ep] | None = None
    eligible: set[int] | None = None
    positive: set[int] | None = None
    reasons: dict[int, str] = field(default_factory=dict)
    warnable: dict[int, bool] = field(default_factory=dict)
    restart_gap_min: int | None = None


def rng(a: int, b: int, step: int = 15) -> set[int]:
    return set(range(a, b + 1, step))


EPISODE_FIXTURES = [
    Fixture(
        "F01",
        "simple L1; recovery termination",
        [(0, 100), (15, 90), (30, 65), (45, 60), (60, 62), (75, 75), (90, 80)],
        l1=[(30, 75, R, 60, 3)],
        l2=[],
        single=[(30, 75, R, 60, 3)],
    ),
    Fixture(
        "F02",
        "simple L2 nested in L1",
        [(0, 100), (15, 80), (30, 60), (45, 50), (60, 52), (75, 58), (90, 72), (105, 75)],
        l1=[(30, 90, R, 50, 4)],
        l2=[(45, 75, R, 50, 2)],
    ),
    Fixture(
        "F03",
        "exactly two consecutive lows",
        [(0, 100), (15, 68), (30, 66), (45, 72), (60, 74)],
        l1=[(15, 45, R, 66, 2)],
    ),
    Fixture(
        "F04",
        "isolated lows are not L1; single-reading rule merges until 2 recoveries",
        [(0, 100), (15, 65), (30, 72), (45, 68), (60, 71), (75, 73)],
        l1=[],
        single=[(15, 60, R, 65, 3)],
    ),
    Fixture(
        "F05",
        "two lows 25 min apart do not confirm onset",
        [(0, 100), (15, 65), (40, 66), (55, 75), (70, 80)],
        l1=[],
        single=[(15, 55, R, 65, 2)],
    ),
    Fixture(
        "F06",
        "onset at recording start",
        [(0, 60), (15, 62), (30, 75), (45, 78)],
        l1=[(0, 30, R, 60, 2)],
    ),
    Fixture(
        "F07",
        "onset near recording end -> record_end",
        [(0, 100), (15, 95), (30, 66), (45, 64)],
        l1=[(30, None, E, 64, 2)],
    ),
    Fixture(
        "F08",
        "a single >=70 reading does not end an episode",
        [(0, 100), (15, 65), (30, 60), (45, 72), (60, 66), (75, 71), (90, 73)],
        l1=[(15, 75, R, 60, 4)],
    ),
    Fixture(
        "F09",
        "gap > 30 min ends the episode; single rule restarts after the gap",
        [(0, 100), (15, 65), (30, 62), (75, 64), (90, 80), (105, 85)],
        l1=[(15, 75, G, 62, 2)],
        single=[(15, 75, G, 62, 2), (75, 90, R, 64, 1)],
    ),
    Fixture(
        "F09b",
        "gap of exactly 30 min does NOT end the episode",
        [(0, 100), (15, 65), (30, 62), (60, 64), (75, 80), (90, 85)],
        l1=[(15, 75, R, 62, 3)],
    ),
    Fixture(
        "F10",
        "a final lone >=70 reading cannot confirm recovery -> record_end",
        [(0, 100), (15, 65), (30, 62), (45, 75)],
        l1=[(15, None, E, 62, 3)],
    ),
    Fixture(
        "F11",
        "multiple separate episodes",
        [
            (0, 100),
            (15, 65),
            (30, 60),
            (45, 75),
            (60, 80),
            (75, 100),
            (90, 66),
            (105, 64),
            (120, 78),
            (135, 80),
        ],
        l1=[(15, 45, R, 60, 2), (90, 120, R, 64, 2)],
    ),
    Fixture(
        "F12",
        "adjacent episodes: relapse right after confirmed recovery",
        [(0, 65), (15, 60), (30, 72), (45, 74), (60, 66), (75, 62), (90, 75), (105, 77)],
        l1=[(0, 30, R, 60, 2), (60, 90, R, 62, 2)],
    ),
    Fixture(
        "F13a",
        "exactly 70 mg/dL is not low",
        [(0, 100), (15, 70), (30, 70), (45, 100)],
        l1=[],
        single=[],
    ),
    Fixture(
        "F13b",
        "exactly 70 mg/dL counts toward recovery",
        [(0, 100), (15, 65), (30, 60), (45, 70), (60, 70), (75, 100)],
        l1=[(15, 45, R, 60, 2)],
    ),
    Fixture(
        "F14",
        "exactly 54 mg/dL is not an L2 low",
        [(0, 100), (15, 60), (30, 54), (45, 54), (60, 53.9), (75, 52), (90, 72), (105, 80)],
        l1=[(15, 90, R, 52, 5)],
        l2=[(60, 90, R, 52, 2)],
    ),
    Fixture(
        "F15",
        "sensor-floor readings are lows (never excluded)",
        [(0, 100), (15, 39.6), (30, 39.6), (45, 45), (60, 72), (75, 75)],
        l1=[(15, 60, R, 39.6, 3)],
        l2=[(15, 60, R, 39.6, 3)],
    ),
    Fixture(
        "F18a",
        "irregular sampling (14/16-min intervals)",
        [(0, 100), (14, 66), (30, 64), (44, 72), (59, 74)],
        l1=[(14, 44, R, 64, 2)],
    ),
    Fixture(
        "F18b",
        "onset spacing exactly 20 min confirms",
        [(0, 100), (10, 66), (30, 64), (45, 75), (60, 80)],
        l1=[(10, 45, R, 64, 2)],
    ),
    Fixture(
        "F18c",
        "onset spacing 21 min does not confirm",
        [(0, 100), (10, 66), (31, 64), (46, 75), (61, 80)],
        l1=[],
    ),
    Fixture(
        "F18d",
        "recovery pair 25 min apart does not confirm recovery (executable spec)",
        [(0, 100), (15, 65), (30, 60), (45, 75), (70, 78), (85, 80)],
        l1=[(15, 70, R, 60, 3)],
    ),
    Fixture(
        "F19",
        "long gap, then resumed monitoring with an episode",
        [*steady(0, 120), (320, 65), (335, 62), (350, 80), (365, 82)],
        l1=[(320, 350, R, 62, 2)],
    ),
]

ELIGIBILITY_FIXTURES = [
    Fixture(
        "E01",
        "warm-up (>=120 min since start) and insufficient follow-up",
        steady(0, 300),
        l1=[],
        eligible=rng(120, 240),
        positive=set(),
        reasons={
            105: "INSUFFICIENT_HISTORY",
            120: "ELIGIBLE",
            255: "INSUFFICIENT_FOLLOW_UP",
            300: "INSUFFICIENT_FOLLOW_UP",
        },
    ),
    Fixture(
        "E02",
        "missing readings -> fewer than 7 readings in (t-120, t]",
        [*steady(0, 120), *steady(165, 405)],
        l1=[],
        eligible={120} | rng(255, 345),
        positive=set(),
        reasons={
            165: "INSUFFICIENT_HISTORY",
            240: "INSUFFICIENT_HISTORY",
            360: "INSUFFICIENT_FOLLOW_UP",
        },
    ),
    Fixture(
        "E03",
        "positive window (t, t+60] incl. onset exactly +60; refractory [end, end+60)",
        [*steady(0, 180), (195, 66), (210, 64), *steady(225, 405)],
        l1=[(195, 225, R, 64, 2)],
        eligible=rng(120, 180) | rng(285, 345),
        positive=rng(135, 180),
        reasons={195: "LOW_CGM", 225: "REFRACTORY", 270: "REFRACTORY", 285: "ELIGIBLE"},
        warnable={195: True},
    ),
    Fixture(
        "E04",
        "onset just beyond +60 (61 min) is negative",
        [*steady(0, 120), (134, 100), *steady(150, 180), (195, 66), (210, 64), *steady(225, 405)],
        l1=[(195, 225, R, 64, 2)],
        eligible={120, 134, 150, 165, 180} | rng(285, 345),
        positive={150, 165, 180},
    ),
    Fixture(
        "E05",
        "a >=70 reading inside an active episode is not a prediction time",
        [
            *steady(0, 180),
            (195, 66),
            (210, 62),
            (225, 72),
            (240, 64),
            (255, 75),
            (270, 78),
            *steady(285, 420),
        ],
        l1=[(195, 255, R, 62, 4)],
        eligible=rng(120, 180) | rng(315, 360),
        positive=rng(135, 180),
        reasons={
            225: "IN_EPISODE",
            240: "LOW_CGM",
            255: "REFRACTORY",
            300: "REFRACTORY",
            315: "ELIGIBLE",
            375: "INSUFFICIENT_FOLLOW_UP",
        },
    ),
    Fixture(
        "E06",
        "floor readings: current low (LOW NOW) is never a forecasting target",
        [
            *steady(0, 180),
            (195, 39.6),
            (210, 39.6),
            *steady(225, 315),
            (330, 39.6),
            *steady(345, 480),
        ],
        l1=[(195, 225, R, 39.6, 2)],
        eligible=rng(120, 180) | {285, 300, 315} | rng(345, 420),
        positive=rng(135, 180),
        reasons={195: "LOW_CGM", 210: "LOW_CGM", 330: "LOW_CGM", 345: "ELIGIBLE"},
    ),
    Fixture(
        "E07",
        "onset within the horizon makes t eligible despite < 60 min follow-up",
        [*steady(0, 300), (315, 66), (330, 64)],
        l1=[(315, None, E, 64, 2)],
        eligible=rng(120, 300),
        positive={255, 270, 285, 300},
    ),
    Fixture(
        "E08",
        "gap-terminated episode: refractory from the first post-gap reading",
        [*steady(0, 180), (195, 66), (210, 64), *steady(255, 450)],
        l1=[(195, 255, G, 64, 2)],
        eligible=rng(120, 180) | rng(345, 390),
        positive=rng(135, 180),
        reasons={
            255: "REFRACTORY",
            300: "REFRACTORY",
            315: "INSUFFICIENT_HISTORY",
            330: "INSUFFICIENT_HISTORY",
            345: "ELIGIBLE",
        },
    ),
    Fixture(
        "E09",
        "history window is half-open: the reading at t-120 does not count",
        [
            (0, 100),
            (30, 100),
            (45, 100),
            (60, 100),
            (75, 100),
            (90, 100),
            (120, 100),
            *steady(135, 300),
        ],
        l1=[],
        eligible=rng(135, 240),
        positive=set(),
        reasons={120: "INSUFFICIENT_HISTORY", 135: "ELIGIBLE"},
    ),
    Fixture(
        "E10",
        "sensor replacement gap (212 min), blueprint rule (P-C7 not applied)",
        [*steady(0, 105), *steady(317, 602)],
        l1=[],
        eligible=rng(407, 542),
        positive=set(),
        reasons={392: "INSUFFICIENT_HISTORY", 407: "ELIGIBLE"},
    ),
    Fixture(
        "E10b",
        "same trace with the P-C7 hook enabled (warm-up restarts after gap > 120 min)",
        [*steady(0, 105), *steady(317, 602)],
        l1=[],
        eligible=rng(437, 542),
        positive=set(),
        reasons={422: "INSUFFICIENT_HISTORY", 437: "ELIGIBLE"},
        restart_gap_min=120,
    ),
    Fixture(
        "E11",
        "positive with lead < 15 min: labelled positive but onset is NOT warnable",
        [*steady(0, 120), (125, 100), (130, 66), (145, 64), *steady(160, 400)],
        l1=[(130, 160, R, 64, 2)],
        reasons={120: "ELIGIBLE", 125: "ELIGIBLE"},
        warnable={130: False},
    ),
]

# Checklist of the S2 brief -> fixtures (each item covered at least once).
COVERAGE = {
    1: "F01",
    2: "F02",
    3: "F03",
    4: "F04",
    5: "F05 F18c",
    6: "F06",
    7: "F07",
    8: "F01 F08",
    9: "F09",
    10: "F07 F10",
    11: "F11",
    12: "F12",
    13: "F13a F13b",
    14: "F14",
    15: "F15 E06",
    16: "test_missing_cgm_row",
    17: "test_duplicate_timestamps_*",
    18: "F18a-d",
    19: "F19 E10",
    20: "E03 E05 E08",
    21: "E03",
    22: "E03",
    23: "E04",
    24: "E05",
    25: "E01 E02 E09",
    26: "E01",
    27: "E07",
    28: "test_multiple_recordings_*",
    29: "test_multiple_recordings_*",
    30: "E10 E10b",
}
