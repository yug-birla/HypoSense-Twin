"""Integrated T-only demo walkthrough with screenshots (S8 acceptance). Requires `hyposense serve`.

Case selection: the default ward (first 8 T recordings in catalogue order). The replay is advanced
in 1-hour steps and the FIRST moments at which an ALERT and a LOW NOW occur are captured, so no
case or moment is chosen for how the model performs. Screenshots go to the git-ignored
artifacts/screenshots/walkthrough/.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
OUT = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots" / "walkthrough"


def call(path: str, body: dict | None = None) -> dict:  # type: ignore[type-arg]
    req = urllib.request.Request(
        BASE + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())  # type: ignore[no-any-return]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log: list[str] = []
    with sync_playwright() as p:
        br = p.chromium.launch(channel="msedge")
        page = br.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE + "/")
        page.wait_for_timeout(1200)
        if page.get_by_role("button", name="Change cases").count():  # a replay is loaded
            page.get_by_role("button", name="Change cases").click()
        page.get_by_role("button", name="Start replay").wait_for()
        page.screenshot(path=str(OUT / "01_select_cases.png"))
        page.get_by_role("button", name="Start replay").click()
        page.wait_for_selector("[role=table]")
        page.get_by_role("button", name="Play replay").click()  # visible live updates
        page.wait_for_timeout(4000)
        page.get_by_role("button", name="Pause replay").click()
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "02_ward_live.png"))
        got: dict[str, str] = {}
        for _ in range(24 * 14):
            call("/api/replay/advance", {"seconds": 3600})
            beds = call("/api/ward")["beds"]
            for want in ("ALERT", "LOW_NOW"):
                if want not in got:
                    hit = next((b for b in beds if b["decision"]["state"] == want), None)
                    if hit:
                        got[want] = hit["recording_key"]
                        off = call("/api/replay/status")["offset_s"]
                        log.append(f"first {want}: {hit['recording_key']} at offset {off}s")
                        page.goto(BASE + "/")
                        page.wait_for_selector("[role=table]")
                        page.wait_for_timeout(1000)
                        page.screenshot(path=str(OUT / f"03_ward_first_{want}.png"))
                        page.goto(f"{BASE}/patient/?key={hit['recording_key']}")
                        page.wait_for_selector("section[aria-label='Current state']")
                        page.wait_for_timeout(1500)
                        shot = OUT / f"04_patient_first_{want}.png"
                        page.screenshot(path=str(shot), full_page=True)
            if len(got) == 2:
                break
        key = got.get("ALERT")
        if key:
            page.goto(f"{BASE}/patient/?key={key}")
            page.wait_for_selector("section[aria-label='Current state']")
            btn = page.get_by_role("button", name="Acknowledge…")
            if btn.count():
                btn.first.click()
                page.get_by_role("radio", name="Capillary glucose checked").check()
                page.wait_for_timeout(400)
                page.screenshot(path=str(OUT / "05_acknowledge_dialog.png"))
                page.get_by_role("button", name="Record acknowledgement").click()
                page.wait_for_timeout(1200)
                page.screenshot(path=str(OUT / "06_after_ack.png"), full_page=True)
                log.append("acknowledged one notification (checked_glucose)")
        page.goto(BASE + "/evidence/")
        page.wait_for_selector("text=Model ladder")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "07_evidence.png"), full_page=True)
        br.close()
    print("\n".join(log))


if __name__ == "__main__":
    main()
