"""Ruggrogue per-game adapter (ticket 07 GameAdapter protocol, 20 items).

Static key translation + signal extraction only. The adapter never chooses
actions (ticket 05); the single authorized state branch is the descend-dialog
handshake with its strict boundary.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from gymnasium import spaces
from PIL import Image

from .hud_ocr import HudReader

# Discrete(10) -> physical keys (ticket 05 contract).
ACTION_KEYS: dict[int, list[str]] = {
    0: ["y"],  # NW
    1: ["k"],  # N
    2: ["u"],  # NE
    3: ["h"],  # W
    4: ["l"],  # E
    5: ["b"],  # SW
    6: ["j"],  # S
    7: ["n"],  # SE
    8: ["."],  # wait (natural no-op, always 1 turn)
    9: ["Enter", "h", "Enter"],  # descend macro (dialog handshake)
}

# Keys that must never be injected (ticket 05: Shift+move -> auto_run etc.).
FORBIDDEN_KEYS = {"shift", "control", "ctrl", "alt", "escape"}

# Dialog detection: centered yes/no box region, mean-abs-diff threshold.
# Calibrated: no-dialog Enter -> 0.0 diff; idle -> 0.0. Conservative: erring
# toward "no dialog" yields the safe no-op path (never a wrong descend).
DIALOG_REGION = (0.39, 0.61, 0.375, 0.625)  # fractions of (w0, w1, h0, h1)
DIALOG_DIFF_TOL = 0.02


class RuggrogueAdapter:
    """GameAdapter for ruggrogue v1.0.1 (web)."""

    def __init__(self, manifest_path: Path | None = None) -> None:
        self._hud = HudReader()
        self._manifest_path = manifest_path
        self._baselines: dict = {}

    # -- identity & spaces -------------------------------------------------
    @property
    def name(self) -> str:
        return "ruggrogue"

    @property
    def action_space(self) -> spaces.Space:
        return spaces.Discrete(10, start=0)

    @property
    def observation_space(self) -> spaces.Space:
        h, w = self.frame_shape
        return spaces.Box(low=0, high=255, shape=(h, w), dtype=np.uint8)

    @property
    def frame_shape(self) -> tuple[int, int]:
        return (84, 84)

    # -- launch declarations -----------------------------------------------
    @property
    def launch_url(self) -> str:
        return "http://localhost:8901/index.html"

    @property
    def canvas_selector(self) -> str:
        return "#canvas"

    @property
    def webgl_required(self) -> bool:
        return True

    def _manifest(self) -> Path:
        if self._manifest_path is not None:
            return self._manifest_path
        here = Path(__file__).resolve()
        root = here.parents[3]  # src/rl_game_agent/envs/ruggrogue.py -> repo root
        return root / "vendor" / "ruggrogue-web" / "MANIFEST.json"

    def required_files(self) -> list[dict[str, str]]:
        data = json.loads(self._manifest().read_text(encoding="utf-8"))
        return data["required_files"]

    # -- reset / reward state ------------------------------------------------
    def reset_keys(self) -> list[str]:
        # Title screen: first menu item (New Game) is selected by default.
        return ["Enter"]

    def reset_reward_state(self) -> None:
        self._baselines = {}

    def seed_baselines(self, hud: dict[str, dict]) -> None:
        self._baselines = {
            k: hud.get(k, {}).get("value") for k in ("Depth", "Level", "Experience", "Health", "Turn")
        }

    def smoke_probe_keys(self) -> list[str]:
        return [".", "l", "j"]

    # -- action translation (static table only) ------------------------------
    def action_to_keys(self, action: int) -> list[str]:
        if action not in ACTION_KEYS:
            raise ValueError(f"invalid action {action!r}")
        keys = list(ACTION_KEYS[action])
        for k in keys:
            if k.lower() in FORBIDDEN_KEYS:
                raise RuntimeError(f"forbidden key in translation table: {k!r}")
        return keys

    def needs_dialog_check(self, action: int) -> bool:
        return action == 9

    def dialog_suffix(self) -> list[str]:
        return ["h", "Enter"]

    def detect_dialog(self, before: Image.Image, after: Image.Image) -> bool:
        """Syntactic check only: did a centered dialog box appear?"""
        w, h = before.size
        x0, x1, y0, y1 = DIALOG_REGION
        box = (int(w * x0), int(y0 * h), int(w * x1), int(y1 * h))
        a = np.asarray(before.crop(box).convert("L"), dtype=np.float32)
        b = np.asarray(after.crop(box).convert("L"), dtype=np.float32)
        return bool(np.mean(np.abs(a - b)) / 255.0 > DIALOG_DIFF_TOL)

    # -- signal extraction ----------------------------------------------------
    def read_hud(self, shot: Image.Image) -> dict[str, dict]:
        return self._hud.read_hud(shot)

    def detect_phase(self, shot: Image.Image, hud: dict[str, dict]) -> str:
        """DUNGEON if the HUD reads (or its labels are visible); else GAMEOVER.

        TITLE exists only in the reset flow (fresh load by construction); any
        non-dungeon full-screen state reached mid-episode is the game-over
        stats screen, so it maps to GAMEOVER.
        """
        depth = hud.get("Depth", {})
        turn = hud.get("Turn", {})
        if depth.get("certain") and turn.get("certain"):
            return "DUNGEON"
        if self._hud.hud_labels_present(shot):
            # Torn frame: labels visible but values unreadable; still dungeon.
            return "DUNGEON"
        return "GAMEOVER"

    def on_frame(
        self, prev_hud: dict[str, dict], cur_hud: dict[str, dict], ctx: dict
    ) -> dict:
        """Atomic frame hook -> {reward, terminated, truncated, reason, diag}.

        Ticket 05: reward stays 0.0 (placeholder); ticket 06 fills the formula.
        Termination/truncation structure is final.
        """
        terminated = bool(ctx.get("terminated", False))
        truncated = bool(ctx.get("truncated", False))
        reason = ctx.get("end_reason") or ctx.get("fault")
        return {
            "reward": 0.0,  # placeholder until ticket 06 wires the formula
            "terminated": terminated,
            "truncated": truncated,
            "reason": reason,
            "diag": {
                "reward_breakdown": {},
                "truncated_kind": ctx.get("truncated_kind"),
                "dialog_seen": ctx.get("dialog_seen", False),
            },
        }


def make_adapter() -> RuggrogueAdapter:
    return RuggrogueAdapter()
