"""B4 probe: headless Chromium WebGL gate + canvas element screenshot.

Usage: .venv/bin/python .scratch/ruggrogue-v1/probes/b4_probe.py [--url URL]
Exit 0 = WebGL OK and canvas screenshot non-blank. Exit 2 = B4 blocked.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ARTIFACTS = Path("artifacts/b4")
CANVAS_SELECTOR = "#canvas"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8901/index.html")
    args = ap.parse_args()

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "url": args.url,
        "canvas_selector": CANVAS_SELECTOR,
    }
    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            report["chromium_version"] = browser.version
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on("console", lambda m: errors.append(f"console-{m.type}: {m.text}") if m.type == "error" else None)

            page.goto(args.url, wait_until="load", timeout=30000)
            page.wait_for_selector(CANVAS_SELECTOR, timeout=15000)

            # WebGL gate probe (ticket 04 decision: hard gate on headless WebGL)
            webgl = page.evaluate(
                """() => {
                    const c = document.createElement('canvas');
                    const gl2 = c.getContext('webgl2');
                    const gl1 = c.getContext('webgl');
                    let renderer = null;
                    const gl = gl2 || gl1;
                    if (gl) {
                        const dbg = gl.getExtension('WEBGL_debug_renderer_info');
                        if (dbg) renderer = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
                    }
                    return {webgl2: !!gl2, webgl1: !!gl1, renderer};
                }"""
            )
            report["webgl"] = webgl
            if not (webgl["webgl2"] or webgl["webgl1"]):
                report["verdict"] = "B4_BLOCKED"
                report["reason"] = "headless WebGL unavailable"
                report["errors"] = errors
                _write(report)
                print("B4 BLOCKED: headless WebGL unavailable", file=sys.stderr)
                return 2

            # Let the game boot and render something, then element-screenshot.
            page.wait_for_timeout(4000)
            canvas = page.locator(CANVAS_SELECTOR)
            shot_path = ARTIFACTS / "canvas.png"
            canvas.screenshot(path=str(shot_path))

            box = canvas.bounding_box()
            report["canvas_box"] = box
            report["screenshot"] = str(shot_path)
            report["errors"] = errors

            # Non-blank check: sample pixel variance via PIL-free raw read.
            from PIL import Image  # noqa: PLC0415

            img = Image.open(shot_path).convert("L")
            hist = img.histogram()
            non_empty_bins = sum(1 for h in hist if h > 0)
            report["gray_bins_used"] = non_empty_bins
            if non_empty_bins < 4:
                report["verdict"] = "B4_BLOCKED"
                report["reason"] = "canvas screenshot looks blank"
                _write(report)
                print("B4 BLOCKED: canvas screenshot blank", file=sys.stderr)
                return 2

            report["verdict"] = "OK"
            _write(report)
            print(f"B4 OK: {shot_path} ({img.size}, {non_empty_bins} gray bins), "
                  f"chromium {report['chromium_version']}, webgl={webgl}")
            return 0
        finally:
            browser.close()


def _write(report: dict) -> None:
    (ARTIFACTS / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
