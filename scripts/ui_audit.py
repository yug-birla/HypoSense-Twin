"""Frontend accessibility (axe-core, WCAG 2 A/AA rules) and load-performance audit on the real UI.
Requires `hyposense serve` with a replay selected. Writes an aggregate-only report to
experiments/runs/T-AGG-s8-ui-audit-<ts>/results.json (no patient data).
Usage: uv run python scripts/ui_audit.py [--base http://127.0.0.1:8765]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import urllib.request
from typing import Any

from playwright.sync_api import sync_playwright

from hyposense.common.config import REPO_ROOT
from hyposense.common.hashing import sha256_json
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.evaluation.m0_run import provenance

AXE = REPO_ROOT / "frontend" / "node_modules" / "axe-core" / "axe.min.js"
OUT_DIR = REPO_ROOT / "frontend" / "out" / "_next" / "static"


def _get(base: str, path: str) -> Any:
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    a = ap.parse_args()
    beds = _get(a.base, "/api/ward")["beds"]
    if not beds:
        raise SystemExit("select a replay first")
    key = beds[0]["recording_key"]
    pages = {"ward": "/", "patient": f"/patient/?key={key}", "evidence": "/evidence/"}
    ready = {
        "ward": "[role=table]",
        "patient": "section[aria-label='Current state']",
        "evidence": "text=Model ladder",
    }
    results: dict[str, Any] = {}
    with sync_playwright() as p:
        br = p.chromium.launch(channel="msedge")
        for name, path in pages.items():
            page = br.new_page(viewport={"width": 1440, "height": 900})
            js_bytes = 0

            def on_resp(r: Any) -> None:
                nonlocal js_bytes
                if r.url.endswith(".js"):
                    with contextlib.suppress(Exception):
                        js_bytes += len(r.body())

            page.on("response", on_resp)
            page.goto(a.base + path)
            page.wait_for_selector(ready[name], timeout=30_000)
            t = page.evaluate(
                "() => { const n = performance.getEntriesByType('navigation')[0];"
                " return {dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd,"
                " now: performance.now()} }"
            )
            page.wait_for_timeout(800)
            page.add_script_tag(path=str(AXE))
            axe = page.evaluate(
                "async () => { const r = await axe.run(document, {runOnly: {type: 'tag', values: "
                "['wcag2a','wcag2aa','wcag21a','wcag21aa']}}); return r.violations.map(v => "
                "({id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help})) }"
            )
            # keyboard: the first Tab reaches the skip link, focus is visible
            page.keyboard.press("Tab")
            focus = page.evaluate(
                "() => document.activeElement && document.activeElement.textContent"
            )
            results[name] = {
                "dom_content_loaded_ms": round(t["dcl"], 1),
                "ready_ms": round(t["now"], 1),
                "js_bytes_loaded": js_bytes,
                "axe_violations": axe,
                "first_tab_target": (focus or "").strip()[:40],
            }
            page.close()
        br.close()
    total_js = sum(f.stat().st_size for f in OUT_DIR.rglob("*.js"))
    det = {
        "pages": {
            k: {"axe_violations": v["axe_violations"], "first_tab_target": v["first_tab_target"]}
            for k, v in results.items()
        },
        "axe_version": json.loads((AXE.parent / "package.json").read_text("utf-8"))["version"],
    }
    run_id = make_run_id("T-AGG-s8-ui-audit")
    out = REPO_ROOT / "experiments" / "runs" / run_id
    out.mkdir(parents=True)
    doc = {
        "run_id": run_id,
        "created_utc": utc_now_iso(),
        "status": "DEVELOPMENT (engineering)",
        "results_sha256": sha256_json(det),
        "provenance": provenance({"browser": "msedge (Playwright)", "viewport": "1440x900"}),
        "results": det,
        "timing": {
            k: {kk: vv for kk, vv in v.items() if kk != "axe_violations"}
            for k, v in results.items()
        },
        "static_js_bytes_total": total_js,
    }
    (out / "results.json").write_text(json.dumps(doc, indent=1) + "\n", "utf-8", newline="\n")
    summary = {
        "run_id": run_id,
        **doc["timing"],
        "violations": {k: v["axe_violations"] for k, v in results.items()},
        "static_js_bytes_total": total_js,
    }
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
