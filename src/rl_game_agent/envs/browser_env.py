"""Browser-driven Gymnasium environment framework.

`BrowserGameEnv` owns the browser lifecycle, screenshotting, input injection
and the step-completion barrier. All game-specific knowledge lives in a
`GameAdapter` (per-game script); the framework never hardcodes game logic.

Decisions implemented here come from wayfinder tickets 04 (visual
observation), 05 (action contract) and 07 (per-game interface spec).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from gymnasium import Env, spaces
from PIL import Image
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# GameAdapter protocol (ticket 07: 20-item minimal interface)
# ---------------------------------------------------------------------------


class GameAdapter(Protocol):
    """Per-game script: static translation + signal extraction. Never decides."""

    @property
    def name(self) -> str: ...
    @property
    def action_space(self) -> spaces.Space: ...
    @property
    def observation_space(self) -> spaces.Space: ...
    @property
    def launch_url(self) -> str: ...
    @property
    def canvas_selector(self) -> str: ...
    @property
    def webgl_required(self) -> bool: ...
    @property
    def frame_shape(self) -> tuple[int, int]: ...

    def required_files(self) -> list[dict[str, str]]: ...
    def reset_keys(self) -> list[str]: ...
    def reset_reward_state(self) -> None: ...
    def seed_baselines(self, hud: dict[str, dict]) -> None: ...
    def smoke_probe_keys(self) -> list[str]: ...
    def action_to_keys(self, action: int) -> list[str]: ...
    def needs_dialog_check(self, action: int) -> bool: ...
    def dialog_suffix(self) -> list[str]: ...
    def detect_dialog(self, before: Image.Image, after: Image.Image) -> bool: ...
    def detect_phase(self, shot: Image.Image, hud: dict[str, dict]) -> str: ...
    def read_hud(self, shot: Image.Image) -> dict[str, dict]: ...
    def on_frame(self, prev_hud: dict[str, dict], cur_hud: dict[str, dict], ctx: dict) -> dict: ...


# ---------------------------------------------------------------------------
# BrowserGameEnv
# ---------------------------------------------------------------------------

# Step barrier tuning (tickets 04/07; residual risk: measure in impl).
SYNC_TIMEOUT_S = 8.0
SYNC_POLL_S = 0.25
IDENTICAL_FRAMES_S = 0.25
DIALOG_TIMEOUT_S = 0.3
RESET_DUNGEON_TIMEOUT_S = 12.0
KEY_HOLD_S = 0.05


class BrowserGameEnv(Env):
    """Gymnasium Env driving a browser game via Playwright.

    Observation: single grayscale frame (84x84 uint8) of what the player sees.
    One env step = one logical game action (not necessarily one game turn).
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        adapter: GameAdapter,
        viewport: tuple[int, int] = (1280, 800),
        headless: bool = True,
        sync_timeout_s: float = SYNC_TIMEOUT_S,
    ) -> None:
        super().__init__()
        self.adapter = adapter
        self.viewport = viewport
        self.headless = headless
        self.sync_timeout_s = sync_timeout_s

        self.action_space = adapter.action_space
        self.observation_space = adapter.observation_space

        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._canvas = None
        self._episode_over = True
        self._step_count = 0

    # -- lifecycle ------------------------------------------------------

    def _manifest_path(self) -> Path:
        # vendor/ruggrogue-web/MANIFEST.json relative to repo root; also allow
        # override via env var for other deployments.
        import os

        override = os.environ.get("RUGGROGUE_MANIFEST")
        if override:
            return Path(override)
        here = Path(__file__).resolve()
        # src/rl_game_agent/envs/browser_env.py -> repo root
        root = here.parents[3]
        return root / "vendor" / "ruggrogue-web" / "MANIFEST.json"

    def _check_required_files(self) -> None:
        """B1 gate: verify game files exist with matching checksums."""
        manifest = self._manifest_path()
        if not manifest.is_file():
            raise RuntimeError(f"B1 BLOCKED: manifest not found: {manifest}")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        web_dir = manifest.parent
        for entry in data["required_files"]:
            p = web_dir / entry["path"]
            if not p.is_file():
                raise RuntimeError(f"B1 BLOCKED: required file missing: {entry['path']}")
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            if digest != entry["sha256"]:
                raise RuntimeError(
                    f"B1 BLOCKED: checksum mismatch for {entry['path']}: "
                    f"got {digest[:16]}..., want {entry['sha256'][:16]}..."
                )

    def _webgl_gate(self) -> None:
        """B4 gate: headless WebGL must be available (ticket 04)."""
        assert self._page is not None
        probe = self._page.evaluate(
            """() => {
                const c = document.createElement('canvas');
                return {webgl2: !!c.getContext('webgl2'), webgl1: !!c.getContext('webgl')};
            }"""
        )
        if self.adapter.webgl_required and not (probe["webgl2"] or probe["webgl1"]):
            raise RuntimeError(
                "B4 BLOCKED: headless WebGL unavailable "
                "(fallback path is Xvfb+mss, not implemented in v1)"
            )

    def _launch(self) -> None:
        self._check_required_files()
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)

    def _new_run(self) -> None:
        """Fresh browser context + page (no saves, deterministic start)."""
        assert self._browser is not None
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
        self._context = self._browser.new_context(
            viewport={"width": self.viewport[0], "height": self.viewport[1]}
        )
        self._page = self._context.new_page()
        self._page.goto(self.adapter.launch_url, wait_until="load", timeout=30000)
        self._page.wait_for_selector(self.adapter.canvas_selector, timeout=15000)
        self._webgl_gate()
        self._canvas = self._page.locator(self.adapter.canvas_selector)
        # Ensure the game receives keyboard input.
        self._canvas.click()
        self._page.wait_for_timeout(500)

    # -- screenshots / observation ---------------------------------------

    def _shot(self) -> Image.Image:
        assert self._canvas is not None
        from io import BytesIO

        png = self._canvas.screenshot()
        return Image.open(BytesIO(png))

    @staticmethod
    def _to_obs(img: Image.Image, shape: tuple[int, int] = (84, 84)) -> np.ndarray:
        g = img.convert("L").resize((shape[1], shape[0]), Image.LANCZOS)
        return np.asarray(g, dtype=np.uint8)

    @staticmethod
    def _frames_identical(a: Image.Image, b: Image.Image, tol: float = 0.002) -> bool:
        ia = np.asarray(a.convert("L"), dtype=np.float32)
        ib = np.asarray(b.convert("L"), dtype=np.float32)
        return bool(np.mean(np.abs(ia - ib)) / 255.0 < tol)

    # -- input ----------------------------------------------------------

    def _press(self, key: str) -> None:
        assert self._page is not None
        # <50ms hold per ticket 05; press() is down+up with no modifiers.
        self._page.keyboard.down(key)
        self._page.wait_for_timeout(int(KEY_HOLD_S * 1000))
        self._page.keyboard.up(key)

    # -- Gymnasium API ----------------------------------------------------

    def _wait_dungeon(self, timeout_s: float) -> tuple[Image.Image, dict]:
        """Poll until the HUD reads certain (DUNGEON phase)."""
        t0 = time.time()
        last_shot: Image.Image | None = None
        last_hud: dict = {}
        while time.time() - t0 < timeout_s:
            shot = self._shot()
            hud = self.adapter.read_hud(shot)
            last_shot, last_hud = shot, hud
            if self.adapter.detect_phase(shot, hud) == "DUNGEON":
                return shot, hud
            time.sleep(0.3)
        assert last_shot is not None
        return last_shot, last_hud

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if self._browser is None:
            self._launch()
        # Rebuild context once on fault, then fail (ticket 07).
        last_err: Exception | None = None
        for _ in range(2):
            try:
                self._new_run()
                for key in self.adapter.reset_keys():
                    self._press(key)
                shot, hud = self._wait_dungeon(RESET_DUNGEON_TIMEOUT_S)
                if self.adapter.detect_phase(shot, hud) != "DUNGEON":
                    raise RuntimeError("fault: reset did not reach DUNGEON phase")
                self.adapter.reset_reward_state()
                self.adapter.seed_baselines(hud)
                self._episode_over = False
                self._step_count = 0
                return self._to_obs(shot), self._info(hud, phase="DUNGEON")
            except Exception as e:  # noqa: BLE001 - retry once, then surface
                last_err = e
        raise RuntimeError(f"fault: reset failed twice: {last_err}")

    def step(self, action: int):
        if self._episode_over:
            # Behave like most gym envs: start a fresh episode.
            return self.reset()
        if not self.action_space.contains(action):
            raise ValueError(f"invalid action {action!r} for {self.action_space}")
        assert self._page is not None

        keys = self.adapter.action_to_keys(action)
        pre_shot = self._shot()
        pre_hud = self.adapter.read_hud(pre_shot)
        prev_turn = self._int_or_none(pre_hud.get("Turn", {}))
        prev_depth = self._int_or_none(pre_hud.get("Depth", {}))

        t0 = time.time()
        dialog_seen = False

        # -- inject keys (with the authorized dialog handshake for descend) --
        if self.adapter.needs_dialog_check(action):
            self._press(keys[0])
            dialog_seen = self._poll_dialog(pre_shot)
            if dialog_seen:
                for key in self.adapter.dialog_suffix():
                    self._press(key)
        else:
            for key in keys:
                self._press(key)
                time.sleep(0.05)

        # -- completion barrier (ticket 07, four-way) --
        first_post = self._shot()
        terminated = False
        truncated = False
        truncated_kind: str | None = None
        end_reason: str | None = None
        fault: str | None = None

        def barrier_done(shot: Image.Image, hud: dict, elapsed: float) -> str | None:
            phase = self.adapter.detect_phase(shot, hud)
            if phase == "GAMEOVER":
                return "gameover"
            turn = self._int_or_none(hud.get("Turn", {}))
            if turn is not None and prev_turn is not None and turn > prev_turn:
                return "turn"
            depth = self._int_or_none(hud.get("Depth", {}))
            if depth is not None and prev_depth is not None and depth != prev_depth:
                return "depth"
            if elapsed >= IDENTICAL_FRAMES_S and self._frames_identical(first_post, shot):
                return "identical"
            return None

        outcome: str | None = None
        for attempt in range(2):  # ticket 04: retry the wait once, never resend keys
            t1 = time.time()
            while time.time() - t1 < self.sync_timeout_s:
                time.sleep(SYNC_POLL_S)
                shot = self._shot()
                hud = self.adapter.read_hud(shot)
                outcome = barrier_done(shot, hud, time.time() - t0)
                if outcome is not None:
                    break
            if outcome is not None:
                break
        sync_latency_ms = round((time.time() - t0) * 1000, 1)

        if outcome is None:
            truncated = True
            truncated_kind = "fault"
            fault = "sync timeout waiting for turn/depth/gameover barrier"
            shot, hud = first_post, self.adapter.read_hud(first_post)
        elif outcome == "gameover":
            # Confirm: re-shoot after a beat; transient torn frames recover.
            time.sleep(0.4)
            shot2 = self._shot()
            hud2 = self.adapter.read_hud(shot2)
            if self.adapter.detect_phase(shot2, hud2) == "GAMEOVER":
                terminated = True
                end_reason = "gameover"
                shot, hud = shot2, hud2
            else:
                shot, hud = shot2, hud2
        else:
            shot = self._shot()
            hud = self.adapter.read_hud(shot)

        # -- adapter frame hook (reward/termination structure; 06 fills formula)
        frame = self.adapter.on_frame(
            pre_hud,
            hud,
            {
                "terminated": terminated,
                "truncated": truncated,
                "truncated_kind": truncated_kind,
                "end_reason": end_reason,
                "fault": fault,
                "dialog_seen": dialog_seen,
            },
        )

        self._step_count += 1
        if terminated or truncated:
            self._episode_over = True

        info = self._info(
            hud,
            phase="GAMEOVER" if terminated else "DUNGEON",
            truncated_kind=truncated_kind,
            end_reason=end_reason or frame.get("reason"),
            dialog_seen=dialog_seen,
            sync_latency_ms=sync_latency_ms,
            reward_breakdown=frame.get("diag", {}).get("reward_breakdown", {}),
        )
        return (
            self._to_obs(shot),
            float(frame["reward"]),
            bool(terminated or frame.get("terminated", False)),
            bool(truncated or frame.get("truncated", False)),
            info,
        )

    def _poll_dialog(self, before: Image.Image) -> bool:
        """Authorized UI handshake (ticket 05): detect the descend confirm box."""
        t0 = time.time()
        while time.time() - t0 < DIALOG_TIMEOUT_S:
            time.sleep(0.1)
            if self.adapter.detect_dialog(before, self._shot()):
                return True
        return False

    @staticmethod
    def _int_or_none(field: dict) -> int | None:
        if not field.get("certain"):
            return None
        try:
            return int(field["value"])
        except (ValueError, TypeError):
            return None

    def _info(
        self,
        hud: dict,
        phase: str,
        truncated_kind: str | None = None,
        end_reason: str | None = None,
        dialog_seen: bool = False,
        sync_latency_ms: float = 0.0,
        reward_breakdown: dict | None = None,
    ) -> dict[str, Any]:
        def ivalue(name: str) -> int | None:
            return self._int_or_none(hud.get(name, {}))

        return {
            "phase": phase,
            "turn": ivalue("Turn"),
            "depth": ivalue("Depth"),
            "hud_certain": bool(
                hud.get("Turn", {}).get("certain") and hud.get("Depth", {}).get("certain")
            ),
            "reward_breakdown": reward_breakdown or {},
            "end_reason": end_reason,
            "truncated_kind": truncated_kind,
            "obs_stale": False,
            "dialog_seen": dialog_seen,
            "sync_latency_ms": sync_latency_ms,
            "adapter": self.adapter.name,
            "game_seedable": False,
        }

    def close(self) -> None:
        for obj in (self._context, self._browser):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._context = self._page = self._canvas = None
        self._browser = self._pw = None
