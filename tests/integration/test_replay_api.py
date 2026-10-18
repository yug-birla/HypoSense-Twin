"""S7 integration on REAL tuning-partition (T) records with a SYNTHETIC model (fast; no ignored
artefact needed): offline/live parity, deterministic replay, API contract, acknowledgement,
long run, refusal to start. E is never touched (TUNING_ONLY catalogue)."""

from __future__ import annotations

import gc
import json
import tracemalloc
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from hyposense.api.app import create_app
from hyposense.api.service import Service, load_tuning_streams
from hyposense.evaluation.data import GATE_CODES, replay_decisions
from hyposense.evaluation.metrics import notification_indices
from hyposense.features.build import build_recording
from hyposense.features.snapshot import LEVEL_INDEX
from hyposense.models.artifact import ArtifactError, load_artifact
from hyposense.policy.decide import PolicyState
from hyposense.replay.runner import Pipeline
from hyposense.replay.session import DecisionLog, ReplaySession
from hyposense.state.stream import RecordingStream
from tests.unit.artifact_helpers import synthetic_artifact
from tests.unit.state_helpers import BUILDER, CFG, ENGINE, PHARMA


@pytest.fixture(scope="module")
def streams() -> list[RecordingStream]:
    return load_tuning_streams(CFG, PHARMA)


@pytest.fixture(scope="module")
def art(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return synthetic_artifact(
        tmp_path_factory.mktemp("art") / "M1-dev", tau_alert=0.3, tau_watch=0.1
    )


@pytest.fixture(scope="module")
def client(
    art: Path, streams: list[RecordingStream], tmp_path_factory: pytest.TempPathFactory
) -> Any:
    svc = Service(art, streams, log_root=tmp_path_factory.mktemp("logs"))
    return TestClient(create_app(svc, clock=False)), svc


def test_catalogue_is_tuning_partition_only(streams: list[RecordingStream]) -> None:
    from hyposense.data.dataset import AccessScope, load_dataset

    t_patients = {r.identity.patient_key for r in load_dataset(AccessScope.TUNING_ONLY).recordings}
    assert streams and {s.identity.patient_key for s in streams} <= t_patients


@pytest.mark.parametrize("i", [0, 7])
def test_live_replay_equals_offline_pipeline(
    art: Path, streams: list[RecordingStream], i: int
) -> None:
    """Same states, features, probabilities and notifications as the offline path."""
    model = load_artifact(art, CFG, PHARMA)
    st = streams[i]
    s = ReplaySession([st], Pipeline(ENGINE, BUILDER, model))
    s.step(10**6)
    recs = s.runners[0].decisions
    assert not s.runners[0].rejected
    off = build_recording(st, ENGINE, BUILDER)
    ts, codes, _ = replay_decisions(st, ENGINE, model.rules, {})
    assert np.array_equal(off.ts, ts) and [r.decision.ts for r in recs] == ts.tolist()
    q = codes == GATE_CODES[None]
    raw = model.booster.predict(off.X[:, LEVEL_INDEX[model.level]], num_threads=1)
    p = model.calibrator.apply(raw)
    live_p = np.array([np.nan if r.decision.p is None else r.decision.p for r in recs])
    assert np.array_equal(~np.isnan(live_p), q)  # forecast exactly at gate-queried readings
    assert np.array_equal(live_p[q], p[q])  # bitwise equal probabilities
    alert = q & (p >= model.thresholds.tau_alert)
    expected = set(notification_indices(ts, alert, model.rules.cooldown_s).tolist())
    assert {k for k, r in enumerate(recs) if r.decision.notify} == expected
    for k, r in enumerate(recs):  # non-forecast states equal the offline gate
        if not q[k]:
            assert GATE_CODES[r.decision.state] == codes[k]


def test_replay_determinism_identical_decision_log_hash(
    art: Path, streams: list[RecordingStream], tmp_path: Path
) -> None:
    model = load_artifact(art, CFG, PHARMA)
    pipe = Pipeline(ENGINE, BUILDER, model)
    sel = streams[:4]
    out = []
    for k in range(2):
        log = DecisionLog(tmp_path / f"run{k}", {"run": k})
        s = ReplaySession(sel, pipe, log)
        s.step(10**7)
        out.append((log.sha256(), [r.state.digest() for r in s.runners]))
        log.close()
    assert out[0] == out[1]
    lines = (tmp_path / "run0" / "decisions.jsonl").read_text("utf-8").splitlines()
    assert lines and all("utc" not in json.loads(x) for x in lines[:50])


def test_long_run_x600_without_exceptions_or_memory_growth(
    art: Path, streams: list[RecordingStream]
) -> None:
    """Blueprint test_long_run: the longest T recording (>= 14 days) driven by x600 clock ticks
    (0.25 s ticks = 150 s data time); then reset and replay again: no retained growth."""
    model = load_artifact(art, CFG, PHARMA)
    longest = max(streams, key=lambda s: s.events[-1].ts - s.events[0].ts)
    assert longest.events[-1].ts - longest.events[0].ts >= 10 * 86400
    s = ReplaySession([longest], Pipeline(ENGINE, BUILDER, model))
    tracemalloc.start()
    peaks = []
    for _ in range(2):
        while not s.finished:
            s.advance_to(s.offset + 150)
        gc.collect()
        peaks.append(tracemalloc.get_traced_memory()[0])
        assert not s.runners[0].rejected and not s.runners[0].halted
        s.seek(0, None)
    tracemalloc.stop()
    assert peaks[1] <= peaks[0] * 1.10


def test_service_refuses_to_start_on_tampered_artifact(
    art: Path, streams: list[RecordingStream], tmp_path: Path
) -> None:
    d = tmp_path / "bad"
    d.mkdir()
    for f in art.iterdir():
        (d / f.name).write_bytes(f.read_bytes())
    (d / "calibrator.json").write_text('{"method": "platt", "params": {"a": 1, "b": 0}}', "utf-8")
    with pytest.raises(ArtifactError):
        Service(d, streams[:1], log_root=tmp_path / "logs")


def test_api_contract_and_acknowledgement(client: Any, streams: list[RecordingStream]) -> None:
    c, svc = client
    assert c.get("/api/health").json()["artifact_verified"] is True
    meta = c.get("/api/meta").json()
    assert meta["model_status"] == "DEVELOPMENT" and "TUNING" in meta["source"]
    cases = c.get("/api/replay/cases").json()
    assert len(cases) == len(streams) and all(x["partition"] == "T" for x in cases)
    assert (
        c.post(
            "/api/acknowledgements",
            json={"decision_id": "1_0_1@1", "reason": "known", "user_role": "nurse"},
        ).status_code
        == 409
    )
    keys = [x["recording_key"] for x in cases[:3]]
    st = c.post("/api/replay/select", json={"recording_keys": keys}).json()
    assert st["recordings"] == sorted(keys) and st["offset_s"] == 0
    for _ in range(40):
        c.post("/api/replay/advance", json={"seconds": 6 * 3600})
    beds = c.get("/api/ward").json()["beds"]
    assert [b["rank"] for b in beds] == [1, 2, 3]
    for b in beds:
        assert b["decision"]["model_status"] == "DEVELOPMENT"
        if b["decision"]["p"] is None:
            assert b["decision"]["p_text"] is None
    notes = [n for k in keys for n in c.get(f"/api/patients/{k}").json()["notifications"]]
    assert notes, "the synthetic model should have notified at least once on T"
    nid = notes[0]["decision_id"]
    bad_reason = c.post(
        "/api/acknowledgements",
        json={"decision_id": nid, "reason": "gave sugar", "user_role": "nurse"},
    )
    assert bad_reason.status_code == 422  # only the four reason codes
    extra = c.post(
        "/api/acknowledgements",
        json={"decision_id": nid, "reason": "known", "user_role": "nurse", "note": "x"},
    )
    assert extra.status_code == 422  # no free text
    ok = c.post(
        "/api/acknowledgements",
        json={"decision_id": nid, "reason": "checked_glucose", "user_role": "nurse"},
    )
    assert ok.status_code == 201 and ok.json()["reason"] == "checked_glucose"
    again = c.post(
        "/api/acknowledgements", json={"decision_id": nid, "reason": "known", "user_role": "nurse"}
    )
    assert again.status_code == 409
    pv = c.get(f"/api/patients/{keys[0]}").json()
    if pv["last_forecast"] is not None and pv["current"]["p"] is None:
        assert pv["last_forecast"]["is_current"] is False  # never shown as current
    acks = (svc.session.log.directory / "acks.jsonl").read_text("utf-8").splitlines()
    assert len(acks) == 1 and json.loads(acks[0])["decision_id"] == nid


def test_stale_bed_becomes_insufficient_and_is_streamed(
    client: Any, streams: list[RecordingStream]
) -> None:
    """Two recordings of different length: after the shorter one ends, its bed must not keep
    showing its last decision (Table 14.1 'no reading at t'), and the stream says so."""
    import asyncio

    c, svc = client
    by_len = sorted(streams, key=lambda s: s.events[-1].ts - s.events[0].ts)
    short, long_ = by_len[0], by_len[-1]
    c.post(
        "/api/replay/select",
        json={"recording_keys": [short.identity.recording_key, long_.identity.recording_key]},
    )
    q: asyncio.Queue[Any] = asyncio.Queue(100_000)
    svc.subscribers.add(q)
    end = short.events[-1].ts - short.events[0].ts
    for _ in range(end // (6 * 3600) + 2):
        c.post("/api/replay/advance", json={"seconds": 6 * 3600})
    svc.subscribers.discard(q)
    bed = next(
        b
        for b in c.get("/api/ward").json()["beds"]
        if b["recording_key"] == short.identity.recording_key
    )
    assert bed["decision"]["state"] == "INSUFFICIENT_DATA" and bed["decision"]["p"] is None
    assert (
        bed["decision"]["reasons"] == ["NO_RECENT_READING"]
        and bed["decision"]["decision_id"] is None
    )
    pv = c.get(f"/api/patients/{short.identity.recording_key}").json()
    assert pv["factor_groups"] == []  # no explanation next to a non-current state
    assert pv["last_forecast"] is None or pv["last_forecast"]["is_current"] is False
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    last = [
        m
        for m in msgs
        if m["type"] == "bed_state" and m["recording_key"] == short.identity.recording_key
    ][-1]
    assert last["state"] == "INSUFFICIENT_DATA" and last["p"] is None and last["v"] == 1
    lv = c.get(f"/api/patients/{long_.identity.recording_key}").json()
    if lv["current"]["p"] is not None:  # a current forecast is explained and marked current
        assert lv["last_forecast"]["is_current"] is True
        assert lv["last_forecast"]["decision_id"] == lv["current"]["decision_id"]
        assert lv["factor_groups"]


def test_api_bounds_and_safe_errors(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, svc = client
    assert (
        c.post("/api/replay/select", json={"recording_keys": ["../etc/passwd"]}).status_code == 404
    )
    assert c.post("/api/replay/select", json={"recording_keys": ["x"] * 13}).status_code == 422
    assert c.get("/api/patients/..%2F..%2Fsecrets").status_code == 404
    assert c.post("/api/replay/speed", json={"speed": 10**6}).status_code == 422
    assert c.post("/api/replay/step", json={"n": 10**6}).status_code == 422
    assert c.post("/api/replay/seek", json={"offset_s": 10**12}).status_code == 422

    def boom() -> None:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(svc, "ward", boom)
    r = TestClient(create_app(svc, clock=False), raise_server_exceptions=False).get("/api/ward")
    assert r.status_code == 500 and set(r.json()) == {"error", "ref"}
    assert "secret" not in r.text and "Traceback" not in r.text


def test_stream_messages_are_typed_and_versioned(client: Any) -> None:
    c, _ = client
    with c.stream("GET", "/api/stream?max_events=1") as r:
        body = "".join(r.iter_text())
    assert body.startswith("event: session\n")
    msg = json.loads(body.split("data: ", 1)[1])
    assert msg["v"] == 1 and msg["type"] == "session"


def test_slow_subscriber_is_disconnected_not_blocking(client: Any) -> None:
    import asyncio

    _, svc = client
    q = asyncio.Queue(2)  # type: ignore[var-annotated]
    svc.subscribers.add(q)
    for k in range(5):
        svc.publish({"type": "tick", "k": k})
    assert q not in svc.subscribers and q.get_nowait() is None
    assert PolicyState.ALERT.value == "ALERT"


def test_s8_ward_and_patient_fields(client: Any, streams: list[RecordingStream]) -> None:
    c, _ = client
    keys = [s.identity.recording_key for s in streams[:3]]
    c.post("/api/replay/select", json={"recording_keys": keys})
    for _ in range(8):
        c.post("/api/replay/advance", json={"seconds": 6 * 3600})
    beds = c.get("/api/ward").json()["beds"]
    for b in beds:
        assert b["reason"] and b["summary"].startswith(b["decision"]["state"].replace("_", " "))
        if b["decision"]["p"] is None:
            assert "estimated risk" not in b["summary"]
        assert b["trend"]["category"] in (
            None,
            "steady",
            "rising",
            "rising_fast",
            "falling",
            "falling_fast",
        )
        assert set(b["badges"]) <= {"SENSOR_FAULT_SUSPECTED", "RUNNER_HALTED", "INPUT_REJECTED"}
    pv = c.get(f"/api/patients/{keys[0]}").json()
    ts = [p["ts"] for p in pv["timeline"]]
    assert ts == sorted(ts) and ts and pv["now_ts"] - ts[0] <= 24 * 3600
    assert all(p["cgm_mgdl"] > 0 for p in pv["timeline"])
    fts = [e["forecast_ts"] for e in pv["ledger_entries"]]
    assert fts == sorted(fts, reverse=True)
    assert {e["outcome"] for e in pv["ledger_entries"]} <= {
        "LOW_FOLLOWED",
        "NO_LOW",
        "PENDING",
        "OUTCOME_UNKNOWN",
    }
    assert pv["exposure_units"] and all(isinstance(v, str) for v in pv["exposure_units"].values())
    # a synthetic artefact links no development run: evidence is refused, never invented
    assert c.get("/api/evidence").status_code == 404


def test_evidence_view_from_real_artifacts(streams: list[RecordingStream], tmp_path: Path) -> None:
    from hyposense.evaluation.s7_artifact import MODELS_DIR

    found = sorted(MODELS_DIR.glob("M3-dev-*"))
    if not found:
        pytest.skip("no DEVELOPMENT artefact built (hyposense dev artifact)")
    svc = Service(found[-1], streams[:1], log_root=tmp_path)
    ev = TestClient(create_app(svc, clock=False)).get("/api/evidence").json()
    assert ev["status"] == "DEVELOPMENT" and ev["confirmatory"].startswith("PENDING")
    assert set(ev["ladder"]["treated"]["models"]) >= {"M0", "M1", "M2", "M3r", "M3"}
    assert any(g["gate"] == "G3b" and g["status"] == "TRIGGERED" for g in ev["gates"])
    assert len(ev["safeguards"]) >= 2 and ev["limitations"]
    for c in ev["comparisons"].values():
        if c.get("ci95"):
            assert c["excludes_zero"] == (not c["ci95"][0] <= 0.0 <= c["ci95"][1])
    assert any("level rule" in d["label"] for d in ev["diagnostics"])
    assert any("C0" in x for x in ev["limitations"])
    meta = TestClient(create_app(svc, clock=False)).get("/api/meta").json()
    assert meta["pc10_mode"]["value"] == "system_error" and "PENDING" in meta["pc10_mode"]["status"]
