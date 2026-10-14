"""B3 probe: keypress -> turn advancement barrier verification (no OCR needed).

Starts a new game, presses movement/wait keys, and verifies the game responds
via screenshot pixel-diff. Records the key log to prove no Shift/Ctrl/Alt/Esc.
Usage: .venv/bin/python .scratch/ruggrogue-v1/probes/b3_probe.py
Exit 0 = turns advance on movement keys; exit 2 = B3 blocked.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ARTIFACTS = Path("artifacts/b3")
URL = "http://localhost:8901/index.html"
CANVAS = "#canvas"

# Discrete(10) mapping under test (ticket 05 contract)
MOVES = ["y", "k", "u", "h", "l", "b", "j", "n"]  # 0-7
WAIT = "."  # 8
DESCEND_MACRO = ["Enter", "h", "Enter"]  # 9


def shot_diff(a: Path, b: Path) -> float:
    ia = Image.open(a).convert("L")
    ib = Image.open(b).convert("L")
    diff = ImageChops.difference(ia, ib)
    hist = diff.histogram()
    changed = sum(i * h for i, h in enumerate(hist))
    total = ia.size[0] * ia.size[1] * 255
    return changed / total


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report: dict = {"ts": datetime.now(timezone.utc).isoformat()}
    key_log: list[str] = []

    def press(page, key: str) -> None:
        key_log.append(key)
        page.keyboard.press(key)
        page.wait_for_timeout(600)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(URL, wait_until="load", timeout=30000)
            page.wait_for_selector(CANVAS, timeout=15000)
            page.wait_for_timeout(3000)
            canvas = page.locator(CANVAS)

            # New Game: first menu item is selected by default -> Enter.
            press(page, "Enter")
            page.wait_for_timeout(2500)
            canvas.screenshot(path=str(ARTIFACTS / "game_start.png"))

            # Movement keys: each should change the screen (turn advanced or bump).
            results = {}
            prev = ARTIFACTS / "game_start.png"
            for i, key in enumerate(MOVES):
                press(page, key)
                cur = ARTIFACTS / f"move_{i}_{key}.png"
                canvas.screenshot(path=str(cur))
                d = shot_diff(prev, cur)
                results[key] = round(d, 6)
                prev = cur
            report["move_diffs"] = results

            # Wait key: should always advance exactly one turn (screen may or may
            # not change visibly if nothing moves; record only, don't gate on it).
            press(page, WAIT)
            cur = ARTIFACTS / "wait.png"
            canvas.screenshot(path=str(cur))
            report["wait_diff"] = round(shot_diff(prev, cur), 6)

            # Descend macro off-stairs must be a safe no-op (05 contract).
            for k in DESCEND_MACRO:
                press(page, k)
            cur = ARTIFACTS / "descend_macro.png"
            canvas.screenshot(path=str(cur))
            report["descend_macro_diff"] = round(shot_diff(prev, cur), 6)

            report["key_log"] = key_log
            bad = [k for k in key_log if k.lower() in ("shift", "control", "alt", "escape")]
            report["modifier_violation"] = bad

            moved = sum(1 for d in results.values() if d > 0.0001)
            report["keys_with_visible_change"] = moved
            if bad:
                report["verdict"] = "B3_BLOCKED"
                report["reason"] = f"modifier keys injected: {bad}"
                _write(report)
                return 2
            if moved == 0:
                report["verdict"] = "B3_BLOCKED"
                report["reason"] = "no movement key visibly advanced the game (TurnCount probe failed)"
                _write(report)
                print("B3 BLOCKED: turns do not advance", file=sys.stderr)
                return 2
            report["verdict"] = "OK"
            _write(report)
            print(f"B3 OK: {moved}/8 move keys changed the screen; wait_diff={report['wait_diff']}")
            return 0
        finally:
            browser.close()


def _write(report: dict) -> None:
    (ARTIFACTS / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
