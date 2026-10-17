"""Label configuration: the single source of every label constant (Class C, Blueprint Table 5.1).

All durations are held in integer seconds to avoid float boundary errors. Values come from
configs/default.yaml `event` and `eligibility`, which tests/regression locks against the
blueprint.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from hyposense.common.hashing import sha256_json

_MIN = 60


@dataclass(frozen=True)
class LabelConfig:
    l1_threshold_mgdl: float = 70.0
    l2_threshold_mgdl: float = 54.0
    min_run: int = 2
    max_step_s: int = 20 * _MIN
    max_gap_s: int = 30 * _MIN
    horizon_s: int = 60 * _MIN
    min_lead_s: int = 15 * _MIN
    refractory_s: int = 60 * _MIN
    history_s: int = 120 * _MIN
    min_readings_in_history: int = 7
    follow_up_s: int = 60 * _MIN
    min_time_since_start_s: int = 120 * _MIN
    warmup_restart_after_gap_s: int | None = None  # P-C7 hook; None = blueprint rule

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> LabelConfig:
        ev, el = config["event"], config["eligibility"]
        restart = el.get("warmup_restart_after_gap_min")
        return cls(
            l1_threshold_mgdl=float(ev["threshold_mgdl"]),
            l2_threshold_mgdl=float(ev["l2_threshold_mgdl"]),
            min_run=int(ev["min_run"]),
            max_step_s=int(ev["max_step_min"]) * _MIN,
            max_gap_s=int(ev["max_gap_min"]) * _MIN,
            horizon_s=int(ev["horizon_min"]) * _MIN,
            min_lead_s=int(ev["min_lead_min"]) * _MIN,
            refractory_s=int(ev["refractory_min"]) * _MIN,
            history_s=int(el["history_min"]) * _MIN,
            min_readings_in_history=int(el["min_readings_in_history"]),
            follow_up_s=int(el["follow_up_min"]) * _MIN,
            min_time_since_start_s=int(el["min_time_since_start_min"]) * _MIN,
            warmup_restart_after_gap_s=None if restart is None else int(restart) * _MIN,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        return sha256_json(self.as_dict())
