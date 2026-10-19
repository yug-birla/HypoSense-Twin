"""Judge-readiness visual QA in Microsoft Edge: Overview, the full Guided demo (driven through the
real UI and the real replay), Ward, Patient, Evidence and Add patient at 1440 / 1280 / 1024 px.
Replay screenshots show tuning-partition traces, so they go to the git-ignored
artifacts/screenshots/judge/. Usage: uv run python scripts/ui_judge_qa.py [--base URL]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots" / "judge"


def shot(page: Page, name: str, full: bool = True) -> None:
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    log: dict[str, object] = {}
    with sync_playwright() as p:
        br = p.chromium.launch(channel="msedge")
        page = br.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(a.base + "/")
        expect(page.get_by_role("heading", name="HypoSense Twin")).to_be_visible()
        shot(page, "01_overview_1440")
        # guided demo through the UI
        page.goto(a.base + "/demo/")
        shot(page, "02_demo_intro")
        page.get_by_role("button", name="Start the guided demo").click()
        dock = page.get_by_role("complementary", name="Guided demo")
        expect(dock).to_be_visible()
        demo_msgs: list[str] = []
        for i in range(8):
            expect(dock.get_by_text(f"step {i + 1} of 8")).to_be_visible()
            action = (
                dock.get_by_role("button")
                .filter(has_not_text="Back")
                .filter(has_not_text="Next")
                .filter(has_not_text="Finish")
            )
            labels = [b.inner_text() for b in action.all()]
            todo = [x for x in labels if x and x not in ("Done", "Working…")]
            if todo:
                dock.get_by_role("button", name=todo[0]).click()
                expect(dock.get_by_role("status")).to_be_visible(timeout=120_000)
                demo_msgs.append(dock.get_by_role("status").inner_text())
            page.wait_for_timeout(1200)
            shot(page, f"03_demo_step{i + 1}", full=False)
            if i < 7:
                dock.get_by_role("button", name="Next").click()
        log["demo_messages"] = demo_msgs
        dock.get_by_role("button", name="Finish").click()
        # pages at three widths (replay state is whatever the demo left: real data)
        key = page.evaluate("JSON.parse(sessionStorage.getItem('hyposense.demo')||'{}').alertKey")
        log["demo_alert_key"] = key
        for w in (1440, 1280, 1024):
            page.set_viewport_size({"width": w, "height": 900})
            page.goto(a.base + "/ward/")
            shot(page, f"04_ward_{w}")
            if key:
                page.goto(a.base + f"/patient/?key={key}")
                expect(page.get_by_text("What is happening now?")).to_be_visible()
                shot(page, f"05_patient_{w}")
            page.goto(a.base + "/evidence/")
            expect(page.get_by_text("Understand the evidence")).to_be_visible()
            shot(page, f"06_evidence_{w}")
            page.goto(a.base + "/")
            shot(page, f"07_overview_{w}")
        page.set_viewport_size({"width": 1440, "height": 900})
        if key:
            page.goto(a.base + f"/patient/?key={key}&tab=explain")
            page.get_by_role("button", name="After the last alert?").click()
            expect(page.get_by_text("What happened after the last alert?")).to_be_visible()
            ask = page.get_by_role("region", name="Ask about this patient")
            log["ask_after_alert"] = ask.inner_text()
            ask.screenshot(path=str(OUT / "08_ask_after_alert.png"))
            now = page.get_by_role("region", name="What is happening now")
            pill = now.locator("[data-state]").first
            pill.hover()
            page.wait_for_timeout(600)
            shot(page, "09_state_tooltip", full=False)
        page.goto(a.base + "/intake/")
        shot(page, "10_intake_start")
        log["console_errors"] = errors
        br.close()
    (OUT / "judge_qa.json").write_text(json.dumps(log, indent=1) + "\n", "utf-8")
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
