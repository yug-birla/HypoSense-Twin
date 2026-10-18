"""FastAPI application (ADR-008: REST for snapshots and commands, SSE for the replay clock and
decision events). Routes orchestrate `api.service.Service`; they contain no scientific logic.

Safety: strict request validation (Pydantic, extra fields forbidden); recordings are addressed
only by keys from the server's T catalogue (no client paths); errors return a typed body without
stack traces; replay controls are bounded; the service does not start on an artefact mismatch.
Runs fully offline (no external calls).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from hyposense.api import schemas as S
from hyposense.api.service import Conflict, NotFound, Service

log = logging.getLogger("hyposense.api")
TICK_S = 0.25


def create_app(svc: Service, clock: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(_ticker(svc)) if clock else None
        yield
        if task is not None:
            task.cancel()

    app = FastAPI(title="HypoSense Twin API", version=S.API_VERSION, lifespan=lifespan)

    @app.exception_handler(NotFound)
    async def _nf(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"error": "not_found", "detail": str(exc)}, status_code=404)

    @app.exception_handler(Conflict)
    async def _cf(_: Request, exc: Conflict) -> JSONResponse:
        return JSONResponse({"error": "conflict", "detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def _ve(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=422)

    @app.exception_handler(Exception)
    async def _ie(_: Request, exc: Exception) -> JSONResponse:
        ref = uuid.uuid4().hex[:12]
        log.exception("internal error %s", ref)  # server-side only
        return JSONResponse({"error": "internal_error", "ref": ref}, status_code=500)

    @app.get("/api/health", response_model=S.Health)
    async def health() -> S.Health:
        return S.Health(
            status="ok",
            artifact_verified=True,  # a Service only exists with a verified artefact
            model_version=svc.model.model_version,
            model_status=svc.model.status,
        )

    @app.get("/api/meta")
    async def meta() -> dict[str, Any]:
        return svc.meta()

    @app.get("/api/evidence")
    async def evidence() -> dict[str, Any]:
        return svc.evidence()

    @app.get("/api/replay/cases", response_model=list[S.Case])
    async def cases() -> list[S.Case]:
        return svc.cases()

    @app.get("/api/replay/status", response_model=S.ReplayStatus)
    async def status() -> S.ReplayStatus:
        return svc.status()

    @app.post("/api/replay/select", response_model=S.ReplayStatus)
    async def select(req: S.SelectRequest) -> S.ReplayStatus:
        svc.select(req.recording_keys)
        return svc.status()

    @app.post("/api/replay/play", response_model=S.ReplayStatus)
    async def play() -> S.ReplayStatus:
        if svc.session is None:
            raise Conflict("no replay selected")
        svc.playing = not svc.session.finished
        return svc.status()

    @app.post("/api/replay/pause", response_model=S.ReplayStatus)
    async def pause() -> S.ReplayStatus:
        svc.playing = False
        return svc.status()

    @app.post("/api/replay/speed", response_model=S.ReplayStatus)
    async def speed(req: S.SpeedRequest) -> S.ReplayStatus:
        svc.speed = req.speed
        return svc.status()

    @app.post("/api/replay/step", response_model=S.ReplayStatus)
    async def step(req: S.StepRequest) -> S.ReplayStatus:
        svc.step(req.n)
        return svc.status()

    @app.post("/api/replay/advance", response_model=S.ReplayStatus)
    async def advance(req: S.AdvanceRequest) -> S.ReplayStatus:
        svc.advance(req.seconds)
        return svc.status()

    @app.post("/api/replay/seek", response_model=S.ReplayStatus)
    async def seek(req: S.SeekRequest) -> S.ReplayStatus:
        svc.seek(req.offset_s)
        return svc.status()

    @app.post("/api/replay/reset", response_model=S.ReplayStatus)
    async def reset() -> S.ReplayStatus:
        svc.reset()
        return svc.status()

    @app.get("/api/ward", response_model=S.Ward)
    async def ward() -> S.Ward:
        return svc.ward()

    @app.get("/api/patients/{recording_key}", response_model=S.PatientView)
    async def patient(recording_key: str) -> S.PatientView:
        import re

        if not re.fullmatch(S.RECORDING_KEY, recording_key):
            raise NotFound("unknown recording")
        return svc.patient(recording_key)

    @app.post("/api/acknowledgements", status_code=201)
    async def acknowledge(req: S.AckRequest) -> dict[str, Any]:
        return svc.acknowledge(req)

    @app.get("/api/stream")
    async def stream(max_events: int | None = Query(default=None, ge=1, le=10_000)) -> Any:
        q = svc.subscribe()

        async def gen() -> AsyncIterator[str]:
            n = 0
            try:
                hello = {"v": S.STREAM_VERSION, "type": "session", **svc.status().model_dump()}
                yield _sse(hello)
                n += 1
                while max_events is None or n < max_events:
                    msg = await q.get()
                    if msg is None:  # fell behind: disconnected
                        break
                    yield _sse(msg)
                    n += 1
            finally:
                svc.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def _sse(msg: dict[str, Any]) -> str:
    return f"event: {msg['type']}\ndata: {json.dumps(msg, separators=(',', ':'))}\n\n"


async def _ticker(svc: Service) -> None:
    """Replay clock: advances by wall time x speed while playing. Pacing only, never order."""
    last = time.monotonic()
    while True:
        await asyncio.sleep(TICK_S)
        now = time.monotonic()
        dt, last = now - last, now
        if svc.playing and svc.session is not None:
            try:
                svc.advance(dt * svc.speed)
            except Exception:  # never kill the clock; the runner already logged the error
                log.exception("replay clock tick failed")
                svc.playing = False
