"""README product showcase: screenshots of the real UI on SYNTHETIC new-data sessions only.

Starts its own `hyposense serve` (no replay selected, so no tuning-partition trace appears),
creates SYNTHETIC patients through the public intake API, and captures each main screen in
Microsoft Edge. The trajectories are hand-made SYNTHETIC curves; whatever state the canonical
twin assigns them is shown as is. Usage:
  uv run python scripts/ui_readme_showcase.py [--port 8790]
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots" / "readme"
sys.path.insert(0, str(ROOT))

from tests.unit.intake_helpers import synthetic_frame  # noqa: E402

ANSWERS = {
    "column:0": "ts_local",
    "column:1": "cgm",
    "column:2": "diet_en",
    "unit:cgm": "mg/dL",
    "clock": "local",
}
CONTEXT = {
    "age_y": "64",
    "sex": "female",
    "bmi": "26.1",
    "diabetes_duration_y": "12",
    "hba1c_mmol_mol": "61",
    "egfr": "72",
}


def variant(kind: str) -> pd.DataFrame:
    df = synthetic_frame(days=3)
    n = len(df)
    if kind == "falling":  # last 2 h fall linearly from 150 to 80 mg/dL
        for i, k in enumerate(range(n - 8, n)):
            df.loc[k, "Glucose"] = round(150 - 10 * (i + 1))
    elif kind == "low":  # last hour falls below 70 mg/dL
        for i, k in enumerate(range(n - 4, n)):
            df.loc[k, "Glucose"] = round(96 - 9 * (i + 1))
    elif kind == "gap":  # 3 h without CGM before the final reading
        df.loc[n - 13 : n - 2, "Glucose"] = None
    return df


def api(base: str, method: str, path: str, body: object | None = None) -> dict:  # type: ignore[type-arg]
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(
        base + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(r, timeout=300) as resp:
        return json.loads(resp.read() or b"null")  # type: ignore[no-any-return]


def create(base: str, label: str, df: pd.DataFrame) -> str:
    content = base64.b64encode(df.to_csv(index=False).encode()).decode()
    d = api(
        base,
        "POST",
        "/api/intake/upload",
        {"file_name": "SYNTHETIC.csv", "content_base64": content, "label": label},
    )
    d = api(
        base,
        "POST",
        f"/api/intake/drafts/{d['draft_id']}/answers",
        {"answers": ANSWERS, "context": CONTEXT},
    )
    return str(api(base, "POST", f"/api/intake/drafts/{d['draft_id']}/commit")["recording_key"])


def shot(page: Page, url: str, name: str, tab: str | None = None, h: int = 900) -> None:
    page.set_viewport_size({"width": 1440, "height": h})
    page.goto(url)
    page.get_by_text("Live", exact=True).first.wait_for(timeout=30_000)
    if tab:
        page.get_by_role("tab", name=tab, exact=True).click()
    page.wait_for_timeout(1800)  # charts animate
    page.screenshot(path=str(OUT / f"{name}.png"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    a = ap.parse_args()
    base = f"http://127.0.0.1:{a.port}"
    OUT.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["uv", "run", "hyposense", "serve", "--port", str(a.port)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log: dict[str, object] = {}
    try:
        for _ in range(300):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        for k in ("steady", "falling", "low", "gap"):
            create(base, f"SYNTHETIC-{k}", variant(k))
        beds = api(base, "GET", "/api/ward")["beds"]
        log["states"] = {
            b["label"]: [b["decision"]["state"], b["decision"]["p_text"]] for b in beds
        }
        focus = max(beds, key=lambda b: b["decision"]["p"] or 0)["recording_key"]
        log["focus"] = focus
        with sync_playwright() as p:
            br = p.chromium.launch(channel="msedge")
            page = br.new_page(viewport={"width": 1440, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            pk = f"{base}/patient/?key={focus}"
            shot(page, base + "/", "welcome")
            shot(page, base + "/ward/", "ward", h=1240)
            shot(page, pk + "&tab=overview", "patient_overview", h=1560)
            shot(page, pk + "&tab=medications", "patient_medications", h=1100)
            shot(page, pk + "&tab=twin", "twin_anatomy", h=1340)
            shot(page, pk + "&tab=explain", "explainability", h=1100)
            shot(page, base + "/evidence/", "evidence_overview", h=1200)
            shot(page, base + "/evidence/", "evidence_models", tab="Model comparison", h=1300)
            shot(page, base + "/demo/", "guided_demo")
            log["console_errors"] = errors
            br.close()
    finally:
        proc.terminate()
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-NetTCPConnection -LocalPort {a.port} -State Listen"
                " -ErrorAction SilentlyContinue"
                " | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }",
            ],
            capture_output=True,
        )
    (OUT / "showcase.json").write_text(json.dumps(log, indent=1) + "\n", "utf-8")
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
