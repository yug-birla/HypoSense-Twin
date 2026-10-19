"""New-data intake (product extension): upload → validation → deterministic questions →
canonical parse → live twin → appended observations. SYNTHETIC model and SYNTHETIC recordings
for engineering integration; one REAL tuning-partition (T) recording for the parity test.
E is never touched."""

from __future__ import annotations

import base64
import dataclasses
import io
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from hyposense.api.app import create_app
from hyposense.api.service import Service, load_tuning_streams
from hyposense.data.dataset import extracted_root
from hyposense.data.loader import discover_recordings, read_workbook
from hyposense.data.source import dataset_config
from hyposense.intake.draft import Draft
from hyposense.intake.upload import UploadRejected, read_upload
from hyposense.models.artifact import load_artifact
from hyposense.replay.runner import Pipeline, TwinRunner
from hyposense.state.events import CGMReading
from hyposense.state.stream import RecordingStream, recording_stream
from tests.unit.artifact_helpers import synthetic_artifact
from tests.unit.intake_helpers import synthetic_csv, synthetic_frame
from tests.unit.state_helpers import BUILDER, CFG, ENGINE, PHARMA

ANSWERS = {
    "column:0": "ts_local",
    "column:1": "cgm",
    "column:2": "diet_en",
    "unit:cgm": "mg/dL",
    "clock": "local",
}


@pytest.fixture(scope="module")
def streams() -> list[RecordingStream]:
    return load_tuning_streams(CFG, PHARMA)[:2]


@pytest.fixture(scope="module")
def art(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return synthetic_artifact(
        tmp_path_factory.mktemp("art") / "M1-dev", tau_alert=0.3, tau_watch=0.1
    )


@pytest.fixture()
def client(art: Path, streams: list[RecordingStream], tmp_path: Path) -> Any:
    svc = Service(art, streams, log_root=tmp_path)
    return TestClient(create_app(svc, clock=False)), svc


def _upload(c: TestClient, content: bytes, name: str = "SYNTHETIC.csv") -> dict[str, Any]:
    r = c.post(
        "/api/intake/upload",
        json={"file_name": name, "content_base64": base64.b64encode(content).decode()},
    )
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def _answer(
    c: TestClient, draft: str, answers: dict[str, str], ctx: dict[str, str] | None = None
) -> dict[str, Any]:
    r = c.post(
        f"/api/intake/drafts/{draft}/answers", json={"answers": answers, "context": ctx or {}}
    )
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


# ------------------------------------------------------------------ happy path
def test_upload_questions_session_and_append(client: Any) -> None:
    c, svc = client
    d = _upload(c, synthetic_csv())
    assert d["status"] == "BLOCKED"  # no date/time and CGM columns mapped yet
    qids = {q["id"] for q in d["questions"]}
    assert {"column:0", "column:1", "column:2"} <= qids
    assert next(q for q in d["questions"] if q["id"] == "column:1")["suggested"] is None  # no guess
    d = _answer(c, d["draft_id"], ANSWERS)
    assert d["status"] == "READY"
    med = [q for q in d["questions"] if q["id"].startswith("med:")]
    assert len(med) == 1 and not med[0]["required"]  # "insulin 10u": optional clarification
    assert d["summary"]["cgm_readings"] == 288
    r = c.post(f"/api/intake/drafts/{d['draft_id']}/commit")
    assert r.status_code == 200, r.text
    key = r.json()["recording_key"]
    assert key.startswith("N0001_0_")
    ward = c.get("/api/ward").json()
    bed = next(b for b in ward["beds"] if b["recording_key"] == key)
    assert bed["source"] == "NEW_DATA_SESSION"
    pv = c.get(f"/api/patients/{key}").json()
    assert pv["source"] == "NEW_DATA_SESSION" and pv["model_status"] == "DEVELOPMENT"
    last = pv["now_ts"]
    n_before = len(svc.live[key].runner.decisions)
    r = c.post(
        f"/api/sessions/{key}/observations",
        json={"kind": "cgm", "local_time": "2030-03-04 00:00", "value": 5.0, "unit": "mmol/L"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["events"] == 1 and len(r.json()["decisions"]) == 1
    runner = svc.live[key].runner
    assert len(runner.decisions) == n_before + 1
    ev = runner.stream.events[-1]
    assert isinstance(ev, CGMReading) and ev.value_mgdl == pytest.approx(90.1) and ev.ts > last
    # medication and meal append go through the canonical parser
    r = c.post(
        f"/api/sessions/{key}/observations",
        json={
            "kind": "medication",
            "local_time": "2030-03-04 00:05",
            "column": "insulin_sc",
            "text": "insulin aspart 4u",
        },
    )
    assert r.status_code == 200, r.text
    assert svc.live[key].runner.stream.events[-1].canonical == "insulin_aspart"


def test_out_of_order_and_invalid_observations_are_refused(client: Any) -> None:
    c, _ = client
    d = _answer(c, _upload(c, synthetic_csv())["draft_id"], ANSWERS)
    key = c.post(f"/api/intake/drafts/{d['draft_id']}/commit").json()["recording_key"]
    url = f"/api/sessions/{key}/observations"
    early = c.post(
        url, json={"kind": "cgm", "local_time": "2030-03-02 10:00", "value": 100, "unit": "mg/dL"}
    )
    assert early.status_code == 422 and "append-only" in early.json()["detail"]
    for bad in (
        {"kind": "cgm", "local_time": "2030-03-05 00:00", "value": 100},  # no unit
        {"kind": "cgm", "local_time": "2030-03-05 00:00", "value": 900, "unit": "mg/dL"},
        {"kind": "cgm", "local_time": "05/03/2030", "value": 100, "unit": "mg/dL"},
        {
            "kind": "medication",
            "local_time": "2030-03-05 00:00",
            "column": "insulin_sc",
            "text": "",
        },
        {"kind": "dose_advice", "local_time": "2030-03-05 00:00"},
    ):
        assert c.post(url, json=bad).status_code == 422, bad
    # a historical replay recording cannot be appended to
    assert (
        c.post(
            "/api/sessions/2001_0_20201102/observations",
            json={"kind": "cgm", "local_time": "2030-03-05 00:00", "value": 100, "unit": "mg/dL"},
        ).status_code
        == 404
    )


# ------------------------------------------------------------------ clarification paths
def test_units_are_asked_not_guessed_and_implausible_units_refused(client: Any) -> None:
    c, _ = client
    d = _upload(c, synthetic_csv(mmol=True))
    d = _answer(c, d["draft_id"], {**ANSWERS, "unit:cgm": "mg/dL"})  # wrong unit for mmol data
    assert d["status"] == "BLOCKED"
    assert any(f["code"] == "UNIT_IMPLAUSIBLE" for f in d["findings"])
    d = _answer(c, d["draft_id"], {"unit:cgm": "mmol/L"})
    assert d["status"] == "READY"


def test_explicit_unit_header_and_utc_clock() -> None:
    f = synthetic_frame(glucose_header="Sensor glucose (mmol/L)", mmol=True)
    f["Timestamp"] = [t.replace(" ", "T") + ":00Z" for t in f["Timestamp"]]
    d = Draft("d", "N0009", f, "x.csv")
    d.answers.update({"column:0": "ts_local", "column:1": "cgm", "column:2": "diet_en"})
    r = d.evaluate()
    assert "unit:cgm" not in {q.id for q in r.questions}  # stated in the header
    assert "clock" not in {q.id for q in r.questions}  # timestamps marked UTC
    assert r.status == "NEEDS_ANSWERS"  # the patient's offset is required to convert UTC
    d.answers["patient_utc_offset"] = "+02:00"
    r = d.evaluate()
    assert r.status == "READY" and r.summary["first_local"] == "2030-03-01 02:00"


def test_mixed_time_zones_block() -> None:
    f = synthetic_frame()
    f.loc[0, "Timestamp"] = "2030-03-01T00:00:00+02:00"
    d = Draft("d", "N0009", f, "x.csv")
    d.answers.update(ANSWERS)
    assert any(x.code == "MIXED_TIME_ZONES" for x in d.evaluate().findings)


def test_new_patient_without_data_abstains(client: Any) -> None:
    c, _ = client
    d = c.post("/api/intake/new", json={"label": "SYNTHETIC-B"}).json()
    assert d["status"] == "READY"
    assert any(f["code"] == "NO_OBSERVATIONS" for f in d["findings"])
    key = c.post(f"/api/intake/drafts/{d['draft_id']}/commit").json()["recording_key"]
    pv = c.get(f"/api/patients/{key}").json()
    assert pv["current"]["state"] == "INSUFFICIENT_DATA" and pv["current"]["p"] is None
    for k in range(3):  # a few readings: still no forecast
        r = c.post(
            f"/api/sessions/{key}/observations",
            json={
                "kind": "cgm",
                "local_time": f"2030-01-01 00:{k * 5:02d}",
                "value": 120,
                "unit": "mg/dL",
            },
        )
        assert r.status_code == 200, r.text
    pv = c.get(f"/api/patients/{key}").json()
    assert pv["current"]["p"] is None and pv["label"] == "SYNTHETIC-B"


def test_context_validation(client: Any) -> None:
    c, _ = client
    d = _upload(c, synthetic_csv())
    d = _answer(
        c,
        d["draft_id"],
        ANSWERS,
        {"age_y": "250", "sex": "male", "prescribed_agents": "insulin aspart"},
    )
    assert d["status"] == "READY"
    assert any("age_y" in f["message"] for f in d["findings"] if f["code"] == "CONTEXT_INVALID")
    r = c.post(f"/api/intake/drafts/{d['draft_id']}/answers", json={"context": {"name": "x"}})
    assert r.status_code == 422  # only model-relevant context fields exist


# ------------------------------------------------------------------ invalid files
@pytest.mark.parametrize(
    ("name", "content", "msg"),
    [
        ("a.exe", b"MZ", "unsupported"),
        ("a.csv", b"", "empty"),
        ("a.xlsx", b"not a zip", "signature"),
        ("a.xlsx", b"PK\x03\x04garbage", "cannot be read"),
        ("a.csv", b"a,b\x00\n1,2", "binary"),
        ("a.csv", "Zeit;Wert\n".encode("utf-16"), ""),
        ("a.csv", b"x" * 5_000_001, "exceeds"),
        ("a.csv", b"a,a\n1,2\n", "duplicate"),
    ],
    ids=["exe", "empty", "xlsx-sig", "xlsx-corrupt", "nul", "utf16", "too-large", "dup-header"],
)
def test_unsafe_or_malformed_files_are_rejected(name: str, content: bytes, msg: str) -> None:
    with pytest.raises(UploadRejected, match=msg):
        read_upload(name, content)


def test_path_traversal_name_is_sanitised() -> None:
    t = read_upload("../../etc/passwd.csv", synthetic_csv())
    assert "/" not in t.file_name and ".." not in t.file_name.replace("..csv", "")


def test_xlsx_upload_matches_csv() -> None:
    f = synthetic_frame()
    buf = io.BytesIO()
    f.to_excel(buf, index=False)
    x = Draft("d", "N0009", read_upload("s.xlsx", buf.getvalue()).frame, "s.xlsx")
    c = Draft("d", "N0009", read_upload("s.csv", synthetic_csv()).frame, "s.csv")
    for d in (x, c):
        d.answers.update(ANSWERS)
    rx, rc = x.evaluate(), c.evaluate()
    assert rx.status == rc.status == "READY"
    assert rx.stream is not None and rc.stream is not None
    assert rx.stream.events == rc.stream.events


# ------------------------------------------------------------------ parity + causality
def _strip(e: Any) -> Any:
    kw = {"recording_key": "k"}
    if hasattr(e, "patient_key"):
        kw["patient_key"] = "p"
    return dataclasses.replace(e, **kw)


def test_upload_adapter_equals_historical_adapter(art: Path) -> None:
    """A real T recording exported to CSV and uploaded gives the same canonical events, the same
    twin decisions and the same probabilities as the historical adapter."""
    from hyposense.data.dataset import AccessScope, load_dataset
    from hyposense.medication.dictionary import load_dictionary

    ds = load_dataset(AccessScope.TUNING_ONLY)
    rec = ds.recordings[0]
    path = next(
        p
        for p in discover_recordings(
            extracted_root() / dataset_config()["extract"]["recordings_dir"]
        )
        if p.name == rec.identity.file_name
    )
    _, raw = read_workbook(path)
    csv = raw.to_csv(index=False, date_format="%Y-%m-%d %H:%M:%S").encode("utf-8")
    d = Draft("d", "N0009", read_upload("x.csv", csv).frame, "x.csv")
    d.answers["clock"] = "local"  # the record's clock is the patient's local clock
    for q in d.evaluate().questions:
        if q.id.startswith("unit:"):
            d.answers[q.id] = "mg/dL"
    r = d.evaluate()
    assert r.status == "READY", [(f.code, f.message) for f in r.findings]
    plaus = {k: (float(v[0]), float(v[1])) for k, v in CFG["features"]["static_plausible"].items()}
    hist = recording_stream(rec, load_dictionary(), PHARMA["formulation_rules"], None, plaus)
    assert r.stream is not None
    up = recording_stream(r.recording, load_dictionary(), PHARMA["formulation_rules"], None, plaus)  # type: ignore[arg-type]
    assert [_strip(e) for e in up.events] == [_strip(e) for e in hist.events]
    model = load_artifact(art, CFG, PHARMA)
    pipe = Pipeline(ENGINE, BUILDER, model)
    a, b = TwinRunner(hist, pipe), TwinRunner(up, pipe)
    for j, e in enumerate(hist.events):
        a.feed(j, e)
    for j, e in enumerate(up.events):
        b.feed(j, e)
    sa = [(x.decision.ts, x.decision.state, x.decision.p) for x in a.decisions]
    sb = [(x.decision.ts, x.decision.state, x.decision.p) for x in b.decisions]
    assert sa == sb and len(sa) > 100


def test_session_built_incrementally_equals_full_upload(client: Any) -> None:
    """Causality: a twin built from the first 2 days and then fed day 3 one reading at a time
    makes the same decisions as a twin built from all 3 days at once."""
    c, svc = client
    full = synthetic_frame(days=3)
    full["Insulin dose - s.c."] = None
    full["Meal"] = None
    head = full.iloc[: 2 * 96]
    k_full = _commit_frame(c, full)
    k_head = _commit_frame(c, head)
    for t, v in zip(full["Timestamp"].iloc[2 * 96 :], full["Glucose"].iloc[2 * 96 :], strict=True):
        r = c.post(
            f"/api/sessions/{k_head}/observations",
            json={"kind": "cgm", "local_time": t, "value": float(v), "unit": "mg/dL"},
        )
        assert r.status_code == 200, r.text
    a = [(x.decision.ts, x.decision.state, x.decision.p) for x in svc.live[k_full].runner.decisions]
    b = [(x.decision.ts, x.decision.state, x.decision.p) for x in svc.live[k_head].runner.decisions]
    assert a == b


def _commit_frame(c: TestClient, f: pd.DataFrame) -> str:
    d = _upload(c, f.to_csv(index=False).encode("utf-8"))
    d = _answer(c, d["draft_id"], ANSWERS)
    r = c.post(f"/api/intake/drafts/{d['draft_id']}/commit")
    assert r.status_code == 200, r.text
    return str(r.json()["recording_key"])


def test_delete_session_removes_memory_and_log(client: Any, tmp_path: Path) -> None:
    c, svc = client
    key = _commit_frame(c, synthetic_frame(days=1))
    logdir = svc.live[key].log.directory
    assert logdir.is_dir() and logdir.is_relative_to(tmp_path)
    assert c.delete(f"/api/sessions/{key}").status_code == 204
    assert key not in svc.live and not logdir.exists()
    assert c.get(f"/api/patients/{key}").status_code == 404


def test_intake_never_touches_research_partitions() -> None:
    """New data are never written under data/ and never named like a dataset patient."""
    d = Draft("d", "N0009", synthetic_frame(days=1), "x.csv")
    d.answers.update(ANSWERS)
    r = d.evaluate()
    assert r.stream is not None
    assert r.stream.identity.patient_key == "intake:N0009"
    assert not r.stream.identity.patient_id.isdigit()  # cannot collide with a T/E patient id


def test_ask_intents_are_fixed_and_answer_from_state(client: Any) -> None:
    c, _ = client
    key = _commit_frame(c, synthetic_frame(days=2))
    for intent in (
        "why_state",
        "no_forecast",
        "current",
        "changed",
        "after_alert",
        "medications",
        "quality",
        "missing",
        "evidence",
    ):
        r = c.get(f"/api/patients/{key}/ask", params={"intent": intent})
        assert r.status_code == 200, r.text
        lines = r.json()["lines"]
        assert lines[-1].startswith("This is research decision support")
        text = " ".join(lines).lower()
        assert "you should" not in text and "increase" not in text  # no advice
    meds = c.get(f"/api/patients/{key}/ask", params={"intent": "medications"}).json()["lines"]
    assert any("insulin_aspart" in x for x in meds)
    ev = c.get(f"/api/patients/{key}/ask", params={"intent": "evidence"}).json()["lines"]
    assert any("no accuracy claim" in x for x in ev)
    missing = c.get(f"/api/patients/{key}/ask", params={"intent": "missing"}).json()["lines"]
    assert any("Patient context not available" in x for x in missing)
    assert c.get(f"/api/patients/{key}/ask", params={"intent": "what dose?"}).status_code == 422
