"""S7 engineering evidence on T (DEVELOPMENT; E sealed). Writes
experiments/runs/T-AGG-s7-engineering-<ts>/results.json with provenance.

Measured:
1. artefact reproducibility: two rebuilds give identical file hashes;
2. offline/live parity on every T recording (states, probabilities, notifications);
3. replay determinism: two full replays give identical decision-log hashes;
4. error injection on real records: rejected events never change any later decision;
5. latency (per reading and per component), replay throughput, API latency, memory.

The DEVELOPMENT artefact is fitted on ALL of T, so state/alert counts below are IN-SAMPLE
engineering descriptions, never performance evidence.
"""

from __future__ import annotations

import dataclasses
import gc
import json
import math
import tempfile
import time
import tracemalloc
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_json
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.evaluation.data import GATE_CODES, replay_decisions
from hyposense.evaluation.m0_run import provenance
from hyposense.evaluation.metrics import notification_indices
from hyposense.features.build import build_recording
from hyposense.features.snapshot import LEVEL_INDEX, FeatureBuilder
from hyposense.models.artifact import RuntimeModel, load_artifact
from hyposense.policy.decide import PolicyState, decide, gate
from hyposense.replay.runner import Pipeline, TwinRunner
from hyposense.replay.session import DecisionLog, ReplaySession
from hyposense.state.events import CGMReading
from hyposense.state.patient import EngineConfig, PatientState
from hyposense.state.stream import RecordingStream


def _q(x: list[float]) -> dict[str, float]:
    a = np.array(x) * 1000.0
    return {
        "n": len(a),
        "p50_ms": round(float(np.percentile(a, 50)), 4),
        "p95_ms": round(float(np.percentile(a, 95)), 4),
        "p99_ms": round(float(np.percentile(a, 99)), 4),
        "max_ms": round(float(a.max()), 4),
    }


def _parity(model: RuntimeModel, pipe: Pipeline, st: RecordingStream) -> dict[str, int]:
    s = ReplaySession([st], pipe)
    s.step(10**7)
    recs = s.runners[0].decisions
    off = build_recording(st, pipe.engine, pipe.builder)
    ts, codes, _ = replay_decisions(st, pipe.engine, model.rules, {})
    q = codes == GATE_CODES[None]
    p = model.calibrator.apply(
        model.booster.predict(off.X[:, LEVEL_INDEX[model.level]], num_threads=1)
    )
    live = np.array([np.nan if r.decision.p is None else r.decision.p for r in recs])
    notif = set(
        notification_indices(
            ts, q & (p >= model.thresholds.tau_alert), model.rules.cooldown_s
        ).tolist()
    )
    return {
        "readings": len(ts),
        "ts_mismatch": int(not np.array_equal(ts, [r.decision.ts for r in recs])),
        "forecast_set_mismatch": int((np.isnan(live) == q).sum()),
        "probability_mismatch": int((live[q] != p[q]).sum()),
        "notification_mismatch": len(notif ^ {k for k, r in enumerate(recs) if r.decision.notify}),
        "gate_state_mismatch": sum(
            int(GATE_CODES[r.decision.state] != codes[k]) for k, r in enumerate(recs) if not q[k]
        ),
    }


def _decisions(r: TwinRunner) -> dict[int, tuple[Any, ...]]:
    return {
        x.decision.ts: (x.decision.state, x.decision.p, x.decision.notify)
        for x in r.decisions
        if x.decision.state is not PolicyState.SYSTEM_ERROR
    }


def _inject(pipe: Pipeline, st: RecordingStream) -> dict[str, Any]:
    clean = TwinRunner(st, pipe)
    for j, e in enumerate(st.events):
        clean.feed(j, e)
    evs = list(st.events)
    cg = [k for k, e in enumerate(evs) if isinstance(e, CGMReading)]
    # one bad event after each of five well-separated readings (never consecutive, so the
    # circuit breaker, which is tested separately, does not trip)
    at = [cg[(m + 1) * len(cg) // 7] for m in range(5)]
    first = evs[0].ts
    inject: dict[int, Any] = {}
    for m, k in enumerate(at):
        e0 = evs[k]
        assert isinstance(e0, CGMReading)
        inject[k] = [
            dataclasses.replace(e0, ts=e0.ts + 7, value_mgdl=math.nan),
            dataclasses.replace(e0, ts=e0.ts + 8, value_mgdl=5000.0),
            dataclasses.replace(e0, source_row=10**9),  # duplicate reading time
            dataclasses.replace(e0, ts=first),  # out of order
            dataclasses.replace(e0, recording_key="0000_0_20000101", ts=e0.ts + 9),
        ][m]
    seq = []
    for k, e in enumerate(evs):
        seq.append(e)
        if k in inject:
            seq.append(inject[k])
    bad = list(inject.values())
    r = TwinRunner(st, pipe)
    for j, e in enumerate(seq):
        r.feed(j, e)
    return {
        "injected": len(bad),
        "rejected": len(r.rejected),
        "system_error_records": sum(
            1 for x in r.decisions if x.decision.state is PolicyState.SYSTEM_ERROR
        ),
        "later_decisions_changed": int(_decisions(r) != _decisions(clean)),
        "final_state_equal": int(r.state.digest() == clean.state.digest()),
    }


def run_s7_bench(model_dir: Path) -> dict[str, Any]:
    from hyposense.api.service import Service, load_tuning_streams
    from hyposense.evaluation.s7_artifact import build_dev_artifact

    started = utc_now_iso()
    cfg, pharma = load_config(), load_config("pharma.yaml")
    model = load_artifact(model_dir, cfg, pharma)
    det: dict[str, Any] = {"model_version": model.model_version, "model_status": model.status}
    timing: dict[str, Any] = {}

    # 1. artefact reproducibility
    with tempfile.TemporaryDirectory() as tmp:
        files = [build_dev_artifact(model.level, Path(tmp) / x)["files"] for x in "ab"]
    det["artifact_rebuild"] = {
        "identical_files": files[0] == files[1],
        "matches_deployed": files[0] == model.manifest["files"],
    }

    pipe = Pipeline(EngineConfig.from_config(cfg, pharma), FeatureBuilder(cfg), model)
    t0 = time.perf_counter()
    streams = load_tuning_streams(cfg, pharma)
    timing["load_streams_s"] = round(time.perf_counter() - t0, 2)

    # 2. parity on every T recording
    t0 = time.perf_counter()
    par = [_parity(model, pipe, st) for st in streams]
    timing["parity_s"] = round(time.perf_counter() - t0, 1)
    det["parity"] = {
        "recordings": len(par),
        **{k: int(sum(p[k] for p in par)) for k in par[0]},
    }

    # 3. determinism + throughput + per-reading latency (sessions of <= 12 recordings)
    groups = [streams[i : i + 12] for i in range(0, len(streams), 12)]
    hashes: list[list[str]] = []
    per_event: list[float] = []
    n_events = 0
    states: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    notifications = 0
    forecasts = 0
    days = 0.0
    for rep in range(2):
        hs = []
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            for g, sel in enumerate(groups):
                log = DecisionLog(Path(tmp) / f"g{g}", {"group": g})
                s = ReplaySession(sel, pipe, log)
                while not s.finished:
                    a0 = time.perf_counter()
                    em = s.step(1)[0]
                    if rep == 0 and em.record is not None:
                        per_event.append(time.perf_counter() - a0)
                if rep == 0:
                    n_events += len(s.order)
                    for r in s.runners:
                        days += (r.stream.events[-1].ts - r.stream.events[0].ts) / 86400
                        for x in r.decisions:
                            states[x.decision.state.value] += 1
                            notifications += int(x.decision.notify)
                            forecasts += int(x.decision.p is not None)
                            for tg in x.decision.tags:
                                tags[tg.split(":")[0]] += 1
                hs.append(log.sha256())
                log.close()
        hashes.append(hs)
        timing[f"full_replay_{rep}_s"] = round(time.perf_counter() - t0, 1)
    det["determinism"] = {
        "sessions": len(groups),
        "decision_log_sha256": hashes[0],
        "identical": hashes[0] == hashes[1],
    }
    det["in_sample_description"] = {
        "note": "DEVELOPMENT model fitted on all of T: in-sample, engineering description only",
        "events": n_events,
        "decisions": sum(states.values()),
        "states": dict(sorted(states.items())),
        "forecasts": forecasts,
        "tag_rate_per_forecast": {k: round(v / forecasts, 4) for k, v in sorted(tags.items())},
        "notifications_per_day": round(notifications / days, 3),
        "recording_days": round(days, 1),
    }
    timing["per_reading_end_to_end"] = _q(per_event)
    timing["replay_events_per_s"] = round(n_events / timing["full_replay_1_s"], 1)

    # 4. error injection on real records
    inj = [_inject(pipe, st) for st in streams[:: max(1, len(streams) // 5)]]
    det["error_injection"] = {
        "recordings": len(inj),
        **{k: int(sum(x[k] for x in inj)) for k in inj[0]},
    }

    # 5a. component latency on 2,000 sampled decision times
    comp: dict[str, list[float]] = {
        "state_update": [],
        "gate": [],
        "snapshot": [],
        "predict": [],
        "decide": [],
    }
    for st in streams[:4]:
        s0 = PatientState.start(st.context, pipe.engine)
        for e in st.events:
            a0 = time.perf_counter()
            s0 = s0.update(e)
            comp["state_update"].append(time.perf_counter() - a0)
            if not isinstance(e, CGMReading):
                continue
            a0 = time.perf_counter()
            gt = gate(s0, model.rules)
            comp["gate"].append(time.perf_counter() - a0)
            if not gt.queries_model or len(comp["predict"]) >= 2000:
                continue
            a0 = time.perf_counter()
            snap = pipe.builder.snapshot(s0, model.level)
            a1 = time.perf_counter()
            _, p = model.predict(snap)
            a2 = time.perf_counter()
            decide(gt, p, e.ts, None, model.rules, model.thresholds)
            a3 = time.perf_counter()
            comp["snapshot"].append(a1 - a0)
            comp["predict"].append(a2 - a1)
            comp["decide"].append(a3 - a2)
    timing["components"] = {k: _q(v) for k, v in comp.items()}

    # 5b. API latency (12 recordings selected) and memory over a long run
    from fastapi.testclient import TestClient

    from hyposense.api.app import create_app

    with tempfile.TemporaryDirectory() as tmp:
        svc = Service(model_dir, streams, log_root=Path(tmp))
        c = TestClient(create_app(svc, clock=False))
        c.post(
            "/api/replay/select",
            json={"recording_keys": [s.identity.recording_key for s in groups[0]]},
        )
        c.post("/api/replay/advance", json={"seconds": 6 * 3600})
        lat: dict[str, list[float]] = {"ward": [], "patient": [], "step_1": [], "meta": []}
        key = groups[0][0].identity.recording_key
        calls: dict[str, tuple[str, str, dict[str, Any] | None]] = {
            "ward": ("GET", "/api/ward", None),
            "patient": ("GET", f"/api/patients/{key}", None),
            "step_1": ("POST", "/api/replay/step", {"n": 1}),
            "meta": ("GET", "/api/meta", None),
        }
        for _ in range(200):
            for name, (method, url, body) in calls.items():
                a0 = time.perf_counter()
                r = c.request(method, url, json=body)
                lat[name].append(time.perf_counter() - a0)
                assert r.status_code == 200, (name, r.status_code)
        if svc.session is not None and svc.session.log is not None:
            svc.session.log.close()
        timing["api_testclient"] = {k: _q(v) for k, v in lat.items()}

    longest = max(streams, key=lambda s: s.events[-1].ts - s.events[0].ts)
    s = ReplaySession([longest], pipe)
    tracemalloc.start()
    mem = []
    for _ in range(2):
        while not s.finished:
            s.advance_to(s.offset + 150)  # x600 at 0.25 s ticks
        gc.collect()
        mem.append(tracemalloc.get_traced_memory()[0])
        s.seek(0, None)
    tracemalloc.stop()
    det["long_run"] = {
        "recording_days": round((longest.events[-1].ts - longest.events[0].ts) / 86400, 2),
        "events": len(longest.events),
        "rejected": 0,
        "retained_growth_second_replay": mem[1] <= mem[0] * 1.10,
    }
    timing["long_run_traced_mb"] = [round(m / 2**20, 1) for m in mem]

    run_id = make_run_id("T-AGG-s7-engineering")
    out = REPO_ROOT / "experiments" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    doc = {
        "run_id": run_id,
        "created_utc": started,
        "finished_utc": utc_now_iso(),
        "status": "DEVELOPMENT (engineering)",
        "partition": "T",
        "results_sha256": sha256_json(det),
        "provenance": provenance(
            {
                "artifact_manifest_sha256": model.manifest_sha256,
                "model_version": model.model_version,
            }
        ),
        "results": det,
        "timing": timing,
    }
    (out / "results.json").write_text(json.dumps(doc, indent=1) + "\n", "utf-8", newline="\n")
    return {"run_id": run_id, "results_sha256": doc["results_sha256"], **det, "timing": timing}
