"""E2E (S8): replay -> API -> dashboard -> acknowledgement -> audit log, in a real browser.

Runs the FastAPI app (which serves the static frontend build) in-process with the DEVELOPMENT
artefact and the T catalogue; drives Microsoft Edge with Playwright. Skips when the build, the
artefact or the browser is unavailable. T only; no E data.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

from hyposense.common.config import REPO_ROOT

pytestmark = pytest.mark.e2e
OUT = REPO_ROOT / "frontend" / "out" / "index.html"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Any]]:
    from hyposense.evaluation.s7_artifact import MODELS_DIR

    found = sorted(MODELS_DIR.glob("M3-dev-*"))
    if not OUT.is_file() or not found:
        pytest.skip("needs `npm run build` and `hyposense dev artifact`")
    import uvicorn

    from hyposense.api.app import create_app
    from hyposense.api.service import Service

    svc = Service(found[-1], log_root=tmp_path_factory.mktemp("logs"))
    port = _free_port()
    srv = uvicorn.Server(
        uvicorn.Config(create_app(svc), host="127.0.0.1", port=port, log_level="warning")
    )
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    yield base, svc
    srv.should_exit = True
    th.join(timeout=10)


def _post(base: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        base + path, json.dumps(body).encode(), {"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())  # type: ignore[no-any-return]


def _get(base: str, path: str) -> Any:
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return json.loads(r.read())


def test_replay_dashboard_acknowledge_audit(server: tuple[str, Any]) -> None:
    from playwright.sync_api import Error as PwError
    from playwright.sync_api import sync_playwright

    base, svc = server
    with sync_playwright() as p:
        try:
            br = p.chromium.launch(channel="msedge")
        except PwError:
            pytest.skip("Microsoft Edge not available to Playwright")
        page = br.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/")
        page.get_by_role("button", name="Start replay").click()  # default T selection
        page.wait_for_selector("[role=table]", timeout=30_000)
        rows = page.locator("[role=rowgroup] [role=row]")
        assert rows.count() == 8
        # advance data time until a notification exists (states come from the backend)
        seen: set[str] = set()
        target = None
        for _ in range(40):
            _post(base, "/api/replay/advance", {"seconds": 6 * 3600})
            for b in _get(base, "/api/ward")["beds"]:
                seen.add(b["decision"]["state"])
                if b["unacknowledged_notifications"] and target is None:
                    target = b["recording_key"]
            if target and {"LOW_NOW", "ALERT", "WATCH", "NO_ALERT"} <= seen:
                break
        assert target is not None, "no notification in the T replay"
        # the browser reflects backend state changes (stream-triggered refresh)
        page.wait_for_timeout(1500)
        assert page.get_by_text("NEED ATTENTION", exact=False).count() >= 1
        page.goto(f"{base}/patient/?key={target}")
        page.wait_for_selector("section[aria-label='Current state']", timeout=30_000)
        page.get_by_role("button", name="Acknowledge…").first.click()
        record = page.get_by_role("button", name="Record acknowledgement")
        assert record.is_disabled()
        page.get_by_role("radio", name="Capillary glucose checked").check()
        record.click()
        page.wait_for_selector("text=acknowledged · Capillary glucose checked", timeout=15_000)
        br.close()
    log = svc.session.log.directory / "acks.jsonl"
    acks = [json.loads(x) for x in log.read_text("utf-8").splitlines()]
    assert (
        len(acks) == 1
        and acks[0]["reason"] == "checked_glucose"
        and acks[0]["recording_key"] == target
    )
    assert not errors, errors
    assert {"LOW_NOW", "ALERT", "WATCH", "NO_ALERT"} <= seen
