"""Visual QA of the new-data workflow in Microsoft Edge (Checkpoint B/C evidence).

Drives the REAL UI served by `hyposense serve`: upload a SYNTHETIC CSV → answer the generated
questions → create the twin → Patient review → add observations → Ward board. Uses only the
SYNTHETIC fixture (no patient data), so its screenshots may be shared. Usage:
  uv run python scripts/ui_intake_walkthrough.py [--base http://127.0.0.1:8765]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots" / "intake"
sys.path.insert(0, str(ROOT))

from tests.unit.intake_helpers import synthetic_csv  # noqa: E402


def choose(page: Page, prompt_part: str, value: str) -> None:
    sel = page.get_by_label(prompt_part, exact=False)
    with page.expect_response(lambda r: "/answers" in r.url):
        sel.select_option(value)
    page.wait_for_timeout(150)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    csv = OUT / "SYNTHETIC_recording.csv"
    csv.write_bytes(synthetic_csv())
    log: dict[str, object] = {}
    with sync_playwright() as p:
        br = p.chromium.launch(channel="msedge")
        page = br.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(a.base + "/intake/")
        page.get_by_label("Display label for this patient").fill("SYNTHETIC-demo")
        page.screenshot(path=str(OUT / "01_start.png"), full_page=True)
        page.get_by_label("Recording file").set_input_files(str(csv))
        expect(page.get_by_text("Cannot be accepted yet")).to_be_visible()
        page.screenshot(path=str(OUT / "02_questions_blocked.png"), full_page=True)
        choose(page, "“Timestamp” contain", "ts_local")
        choose(page, "“Glucose” contain", "cgm")
        choose(page, "“Meal” contain", "diet_en")
        choose(page, "Which unit", "mg/dL")
        choose(page, "Which clock", "local")
        expect(page.get_by_text("Ready to create")).to_be_visible()
        page.screenshot(path=str(OUT / "03_answered_ready.png"), full_page=True)
        # clarify the ambiguous medication entry: an invalid answer is refused, a valid one kept
        page.get_by_placeholder("e.g. insulin aspart 6u").fill("insulin glargine")
        page.get_by_role("button", name="Use this entry").click()
        expect(page.get_by_text("Not accepted: still not interpretable")).to_be_visible()
        page.get_by_placeholder("e.g. insulin aspart 6u").fill("insulin glargine 10u")
        page.get_by_role("button", name="Use this entry").click()
        expect(page.get_by_text("Answer: insulin glargine 10u")).to_be_visible()
        page.screenshot(path=str(OUT / "04_medication_clarified.png"), full_page=True)
        page.get_by_role("button", name="Create patient twin").click()
        page.wait_for_url("**/patient/?key=N*")
        expect(page.get_by_text("New data session")).to_be_visible()
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT / "05_patient_new_session.png"), full_page=True)
        key = page.url.split("key=")[1]
        log["recording_key"] = key
        # append a CGM reading (mmol/L, converted by the server) and a dose
        page.get_by_label("Value").fill("4.2")
        page.get_by_label("Unit").select_option("mmol/L")
        page.get_by_role("button", name="Add to twin").click()
        expect(page.get_by_text("Added cgm")).to_be_visible()
        log["after_cgm"] = page.get_by_text("Added cgm").inner_text()
        page.get_by_role("button", name="Why this state?").click()
        expect(page.get_by_text("Why is this patient showing this state?")).to_be_visible()
        page.get_by_role("button", name="What is missing?").click()
        expect(page.get_by_text("What information is missing?")).to_be_visible()
        page.screenshot(path=str(OUT / "05b_patient_after_append_and_ask.png"), full_page=True)
        page.get_by_role("radio", name="CGM reading").click()
        page.get_by_label("Time (patient local, YYYY-MM-DD HH:MM)").fill("2030-03-01 00:00")
        page.get_by_label("Value").fill("100")
        page.get_by_label("Unit").select_option("mg/dL")
        page.get_by_role("button", name="Add to twin").click()
        expect(page.get_by_text("append-only")).to_be_visible()
        page.screenshot(path=str(OUT / "06_observation_refused_out_of_order.png"), full_page=True)
        page.goto(a.base + "/")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "07_ward_with_new_session.png"), full_page=True)
        log["ward_has_new"] = page.get_by_text("New data").count() > 0
        log["console_errors"] = errors
        br.close()
    (OUT / "walkthrough.json").write_text(json.dumps(log, indent=1) + "\n", "utf-8")
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
