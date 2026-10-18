"""Visual QA: drive the real UI (served by `hyposense serve`) in Microsoft Edge; save screenshots.

T-only replay; screenshots show patient-level CGM traces, so they are written to the git-ignored
artifacts/screenshots/ (never committed). Usage:
  uv run python scripts/ui_snapshots.py [--base http://127.0.0.1:8765] [--hours 30]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots"


def post(base: str, path: str, body: dict | None = None) -> dict:  # type: ignore[type-arg]
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body or {}).encode() if body is not None else b"",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())  # type: ignore[no-any-return]


def get(base: str, path: str) -> dict:  # type: ignore[type-arg]
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return json.loads(r.read())  # type: ignore[no-any-return]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--hours", type=float, default=30)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        br = p.chromium.launch(channel="msedge")
        ctx = br.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        # empty state (no replay selected yet, or the picker)
        page.goto(a.base + "/")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / f"{a.tag}01_ward_picker.png"), full_page=True)
        cases = get(a.base, "/api/replay/cases")
        post(
            a.base,
            "/api/replay/select",
            {"recording_keys": [c["recording_key"] for c in cases[:8]]},
        )
        left = a.hours * 3600
        while left > 0:
            post(a.base, "/api/replay/advance", {"seconds": int(min(left, 6 * 3600))})
            left -= 6 * 3600
        for w in (1440, 1280, 1024):
            page.set_viewport_size({"width": w, "height": 900})
            page.goto(a.base + "/")
            page.wait_for_selector("[role=table]", timeout=30000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / f"{a.tag}02_ward_{w}.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 900})
        ward = get(a.base, "/api/ward")
        top = ward["beds"][0]["recording_key"]
        alert = next(
            (
                b["recording_key"]
                for b in ward["beds"]
                if b["decision"]["state"] in ("ALERT", "WATCH")
            ),
            top,
        )
        for name, key in (("top", top), ("forecast", alert)):
            for w in (1440, 1280, 1024):
                page.set_viewport_size({"width": w, "height": 900})
                page.goto(f"{a.base}/patient/?key={key}")
                page.wait_for_selector("section[aria-label='Current state']", timeout=30000)
                page.wait_for_timeout(1200)
                page.screenshot(path=str(OUT / f"{a.tag}03_patient_{name}_{w}.png"), full_page=True)
        for w in (1440, 1024):
            page.set_viewport_size({"width": w, "height": 900})
            page.goto(a.base + "/evidence/")
            page.wait_for_selector("text=Model ladder", timeout=30000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(OUT / f"{a.tag}04_evidence_{w}.png"), full_page=True)
        br.close()
    print(
        json.dumps(
            {"out": str(OUT), "console_errors": errors[:10], "top": top, "forecast": alert},
            indent=1,
        )
    )


if __name__ == "__main__":
    t0 = time.perf_counter()
    main()
    print(f"{time.perf_counter() - t0:.1f}s")
