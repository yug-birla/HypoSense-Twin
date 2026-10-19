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
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, ParamSpec, TypeVar

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from hyposense.api import schemas as S
from hyposense.api.service import Busy, Conflict, InvalidRequest, NotFound, Service
from hyposense.common.config import REPO_ROOT
from hyposense.replay.session import InvalidSelection

log = logging.getLogger("hyposense.api")
FRONTEND_DIR = REPO_ROOT / "frontend" / "out"
TICK_S = 0.25
MAX_TICK_S = 1.0
P = ParamSpec("P")
T = TypeVar("T")  # a stalled loop never turns into one huge clock jump


class Gate:
    """Serialises ALL access to the service. Mutations run in a worker thread so a long seek
    never blocks the event loop (health / meta / stream stay responsive); reads are fast and run
    in the loop, but only between mutations."""

    def __init__(self, svc: Service) -> None:
        self.svc = svc
        self.lock = asyncio.Lock()

    async def mutate(self, fn: Callable[P, T], *args: P.args, **kw: P.kwargs) -> T:
        self.svc.bind_loop(asyncio.get_running_loop())
        async with self.lock:
            return await asyncio.to_thread(fn, *args, **kw)

    async def read(self, fn: Callable[P, T], *args: P.args, **kw: P.kwargs) -> T:
        self.svc.bind_loop(asyncio.get_running_loop())
        async with self.lock:
            return fn(*args, **kw)


def create_app(svc: Service, clock: bool = True) -> FastAPI:
    g = Gate(svc)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(_ticker(g)) if clock else None
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

    @app.exception_handler(InvalidRequest)
    async def _ir(_: Request, exc: InvalidRequest) -> JSONResponse:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=422)

    @app.exception_handler(InvalidSelection)
    async def _is(_: Request, exc: InvalidSelection) -> JSONResponse:
        return JSONResponse({"error": "invalid", "detail": str(exc)}, status_code=422)

    @app.exception_handler(Busy)
    async def _busy(_: Request, exc: Busy) -> JSONResponse:
        return JSONResponse({"error": "busy", "detail": str(exc)}, status_code=503)

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

    @app.get("/api/meta", response_model=S.Meta)
    async def meta() -> dict[str, Any]:
        return svc.meta()

    @app.get("/api/evidence", response_model=S.Evidence)
    async def evidence() -> dict[str, Any]:
        return await g.read(svc.evidence)

    @app.get("/api/confirmatory")
    async def confirmatory() -> dict[str, Any]:
        """S9 result (PENDING until the single official run exists and verifies)."""
        return await g.read(svc.confirmatory)

    @app.get("/api/replay/cases", response_model=list[S.Case])
    async def cases() -> list[S.Case]:
        return await g.read(svc.cases)

    @app.get("/api/replay/status", response_model=S.ReplayStatus)
    async def status() -> S.ReplayStatus:
        return await g.read(svc.status)

    @app.post("/api/replay/select", response_model=S.ReplayStatus)
    async def select(req: S.SelectRequest) -> S.ReplayStatus:
        await g.mutate(svc.select, req.recording_keys)
        return await g.read(svc.status)

    @app.post("/api/replay/play", response_model=S.ReplayStatus)
    async def play() -> S.ReplayStatus:
        def _play() -> None:
            if svc.session is None:
                raise Conflict("no replay selected")
            svc.playing = not svc.session.finished

        await g.read(_play)
        return await g.read(svc.status)

    @app.post("/api/replay/pause", response_model=S.ReplayStatus)
    async def pause() -> S.ReplayStatus:
        def _pause() -> None:
            svc.playing = False

        await g.read(_pause)
        return await g.read(svc.status)

    @app.post("/api/replay/speed", response_model=S.ReplayStatus)
    async def speed(req: S.SpeedRequest) -> S.ReplayStatus:
        def _speed() -> None:
            svc.speed = req.speed

        await g.read(_speed)
        return await g.read(svc.status)

    @app.post("/api/replay/step", response_model=S.ReplayStatus)
    async def step(req: S.StepRequest) -> S.ReplayStatus:
        await g.mutate(svc.step, req.n)
        return await g.read(svc.status)

    @app.post("/api/replay/advance", response_model=S.ReplayStatus)
    async def advance(req: S.AdvanceRequest) -> S.ReplayStatus:
        await g.mutate(svc.advance, req.seconds)
        return await g.read(svc.status)

    @app.post("/api/replay/seek", response_model=S.ReplayStatus)
    async def seek(req: S.SeekRequest) -> S.ReplayStatus:
        await g.mutate(svc.seek, req.offset_s)
        return await g.read(svc.status)

    @app.post("/api/replay/reset", response_model=S.ReplayStatus)
    async def reset() -> S.ReplayStatus:
        await g.mutate(svc.reset)
        return await g.read(svc.status)

    @app.get("/api/ward", response_model=S.Ward)
    async def ward() -> S.Ward:
        return await g.read(svc.ward)

    @app.get("/api/patients/{recording_key}", response_model=S.PatientView)
    async def patient(recording_key: str) -> S.PatientView:
        import re

        if not re.fullmatch(S.RECORDING_KEY, recording_key):
            raise NotFound("unknown recording")
        return await g.read(svc.patient, recording_key)

    @app.post("/api/acknowledgements", status_code=201, response_model=S.AckRecord)
    async def acknowledge(req: S.AckRequest) -> dict[str, Any]:
        return await g.read(svc.acknowledge, req)

    @app.get("/api/stream")
    async def stream(max_events: int | None = Query(default=None, ge=1, le=10_000)) -> Any:
        svc.bind_loop(asyncio.get_running_loop())
        q = await g.read(svc.subscribe)

        async def gen() -> AsyncIterator[str]:
            n = 0
            try:
                st = await g.read(svc.status)
                hello = {"v": S.STREAM_VERSION, "type": "session", **st.model_dump()}
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

    if FRONTEND_DIR.is_dir():  # static export (ADR-007); mounted after the API routes
        app.mount("/", ExportFiles(directory=FRONTEND_DIR, html=True), name="ui")
    return app


def rsc_segment_path(path: str) -> str | None:
    """Next.js static export writes route-segment payloads as `__next.<seg>/__PAGE__.txt` while
    the client requests `__next.<seg>.__PAGE__.txt`. Map the request name onto the exported file
    (one level of segments; anything else is not mapped). Starlette passes an OS-normalised path,
    so both separators are accepted."""
    norm = path.replace("\\", "/")
    head, _, name = norm.rpartition("/")
    if not (name.startswith("__next.") and name.endswith(".txt")):
        return None
    parts = name[len("__next.") : -len(".txt")].split(".")
    if len(parts) != 2 or any(x in ("", "..") for x in parts):
        return None
    if any(x in ("", "..") for x in head.split("/")) and head:
        return None
    mapped = f"__next.{parts[0]}/{parts[1]}.txt"
    return f"{head}/{mapped}" if head else mapped


class ExportFiles(StaticFiles):
    async def get_response(self, path: str, scope: Any) -> Any:
        alt = rsc_segment_path(path)
        try:
            res = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or alt is None:
                raise
            return await super().get_response(alt, scope)
        if res.status_code == 404 and alt is not None:  # html=True serves 404.html instead
            return await super().get_response(alt, scope)
        return res


def _sse(msg: dict[str, Any]) -> str:
    return f"event: {msg['type']}\ndata: {json.dumps(msg, separators=(',', ':'))}\n\n"


async def _ticker(g: Gate) -> None:
    """Replay clock: advances by wall time x speed while playing (dt capped at MAX_TICK_S).
    Pacing only, never order."""
    svc = g.svc
    last = time.monotonic()
    while True:
        await asyncio.sleep(TICK_S)
        now = time.monotonic()
        dt, last = min(now - last, MAX_TICK_S), now
        if svc.playing and svc.session is not None:
            try:
                await g.mutate(svc.advance, dt * svc.speed)
            except Exception:  # never kill the clock; the runner already logged the error
                log.exception("replay clock tick failed")
                svc.playing = False
