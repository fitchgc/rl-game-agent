"""Ruggrogue per-game adapter (ticket 07 GameAdapter protocol, 20 items).

Static key translation + signal extraction only. The adapter never chooses
actions (ticket 05); the single authorized state branch is the descend-dialog
handshake with its strict boundary.

Reward wiring (ticket 06, wayfinder contract):
  per DUNGEON turn: +1.0 x new depth records (ratchet), +0.5 x level-ups,
  +0.001 x xp gain (ignored on level-up turns), -0.01 x hp lost (never reward
  healing), -0.001 step penalty. Terminal: death -1.0 / victory +10.0, latched.
  Truncated: 5000-turn budget (bootstrap), 300-turn stagnation (-0.5),
  20 consecutive OCR failures (reported separately). Priority:
  win/death > budget > stagnation > ocr-fail.
  OCR numerics travel the reward channel only, never the observation.

Certainty is tracked PER FIELD: each signal keeps its own last-certain
baseline and gap flag, so one noisy field never blocks credible diffs from
the others. Delta gates widen on a field's own recovery by certain turns
elapsed (fail-safe: unknown elapsed time keeps the strict single-step bound),
which blocks baseline poisoning by repeated misreads.
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

# Reward contract constants (wayfinder ticket 06).
R_DEPTH_RECORD = 1.0
R_LEVEL_UP = 0.5
R_XP_PER = 0.001
R_DMG_PER = 0.01
R_STEP_PENALTY = 0.001
R_DEATH = -1.0
R_VICTORY = 10.0
R_STAGNATION_PENALTY = 0.5
TURN_BUDGET = 5000
STAGNATION_TURNS = 300
OCR_FAIL_LIMIT = 20

# Internal field keys for the five diffed HUD signals.
FIVE = ("depth", "level", "xp", "hp", "turn")

# Victory detection: top strip of the game-over screen. Victory prints the
# title in GREEN ("* * *  Y O U   W I N !  * * *"), death in MAGENTA
# ("* * * You have been defeated * * *") -- src/modes/game_over.rs.
# The title spans the width, so color must appear in >=2 horizontal thirds:
# a small stray blob can never false-positive to victory.
VICTORY_STRIP_FRac = 0.12


class RuggrogueAdapter:
    """GameAdapter for ruggrogue v1.0.1 (web)."""

    def __init__(self, manifest_path: Path | None = None) -> None:
        self._hud = HudReader()
        self._manifest_path = manifest_path
        self.reset_reward_state()

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
        # Per-field last-certain baselines (the diff source of truth) and
        # per-field gap flags. prev_hud args are informational only.
        self._base: dict[str, int] = {}
        self._fgap: dict[str, bool] = {}
        self._base_max_hp: int | None = None
        self._max_depth: int | None = None
        self._start_turn: int | None = None
        self._last_progress_turn: int | None = None
        self._ocr_fail_streak: int = 0
        self._terminal_issued: bool = False

    def seed_baselines(self, hud: dict[str, dict]) -> None:
        parsed = self._parse_hud(hud)
        self._base = {f: v for f in FIVE if (v := parsed[f][0]) is not None and parsed[f][1]}
        self._fgap = {}
        mh_v, mh_c = parsed["max_hp"]
        self._base_max_hp = mh_v if mh_c else None
        self._max_depth = self._base.get("depth")
        self._start_turn = self._base.get("turn")
        self._last_progress_turn = self._base.get("turn")
        self._ocr_fail_streak = 0
        self._terminal_issued = False

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

    # -- reward machinery (ticket 06) ------------------------------------------

    def _parse_hud(self, hud: dict[str, dict]) -> dict[str, tuple[int | None, bool]]:
        """Parse HUD reads into (value, certain) with per-field credibility gates.

        Gates compare against that field's last certain baseline. When the
        field is recovering from its own gap, multi-turn changes are
        legitimate, so delta gates widen by certain turns elapsed since the
        turn baseline (fail-safe: unknown elapsed time keeps the strict
        single-step bound, which also blocks baseline poisoning by repeated
        misreads).
        """

        def iv(field: str) -> tuple[int | None, bool]:
            f = hud.get(field, {})
            if not f.get("certain"):
                return None, False
            try:
                return int(str(f["value"]).strip()), True
            except (ValueError, TypeError):
                return None, False

        base = self._base
        depth_v, depth_c = iv("Depth")
        level_v, level_c = iv("Level")
        xp_v, xp_c = iv("Experience")
        turn_v, turn_c = iv("Turn")
        hp_v, max_hp_v, hp_c = self._parse_health(hud)

        # Certain turns elapsed since the turn baseline (for relaxed bounds).
        dt: int | None = None
        if turn_c and turn_v is not None:
            bt = base.get("turn")
            if bt is not None:
                if turn_v < bt:
                    turn_c = False  # the turn clock never runs backwards
                else:
                    dt = turn_v - bt

        def bound() -> int:
            return max(1, dt) if dt is not None else 1

        if depth_c and depth_v is not None:
            if depth_v < 1:
                depth_c = False
            else:
                bd = base.get("depth")
                if bd is not None:
                    b = bound() if self._fgap.get("depth") else 1
                    if abs(depth_v - bd) > b:
                        depth_c = False

        if level_c and level_v is not None:
            if level_v < 1:
                level_c = False
            else:
                bl = base.get("level")
                if bl is not None:
                    if level_v < bl:
                        level_c = False
                    else:
                        b = bound() if self._fgap.get("level") else 1
                        if level_v - bl > b:
                            level_c = False

        if xp_c and xp_v is not None:
            if xp_v < 0:
                xp_c = False
            elif not self._fgap.get("xp"):
                bx, bl = base.get("xp"), base.get("level")
                if (
                    bx is not None
                    and bl is not None
                    and level_c
                    and level_v == bl
                    and xp_v < bx
                ):
                    # XP is monotonic within a level; a drop without level-up is noise.
                    xp_c = False

        if hp_c and (hp_v is None or hp_v < 0 or (max_hp_v is not None and hp_v > max_hp_v)):
            hp_c = False

        return {
            "depth": (depth_v, depth_c),
            "level": (level_v, level_c),
            "xp": (xp_v, xp_c),
            "hp": (hp_v, hp_c),
            "max_hp": (max_hp_v, hp_c),
            "turn": (turn_v, turn_c),
        }

    @staticmethod
    def _parse_health(hud: dict[str, dict]) -> tuple[int | None, int | None, bool]:
        f = hud.get("Health", {})
        if not f.get("certain"):
            return None, None, False
        parts = str(f["value"]).split("/")
        if len(parts) != 2:
            return None, None, False
        try:
            return int(parts[0].strip()), int(parts[1].strip()), True
        except (ValueError, TypeError):
            return None, None, False

    def _detect_victory(self, shot: Image.Image | None) -> bool | None:
        """True=win (green title), False=death (magenta title), None=unknown.

        The title spans the frame width, so the winning color must appear in
        >=2 horizontal thirds: a small stray blob can never false-positive to
        victory. Unknown defaults to death downstream: a wrong +10 is worse
        than a wrong -1 for training integrity.
        """
        if shot is None:
            return None
        w, h = shot.size
        strip = np.asarray(
            shot.crop((0, 0, w, max(1, int(h * VICTORY_STRIP_FRac)))).convert("RGB"),
            dtype=np.int32,
        )
        r, g, b = strip[..., 0], strip[..., 1], strip[..., 2]
        green = (g > 120) & (g > r + 40) & (g > b + 40)
        magenta = (r > 120) & (b > 120) & (g < 100)

        def spread(mask: np.ndarray) -> int:
            return sum(
                int(mask[:, s:e].sum()) > 8
                for s, e in ((0, w // 3), (w // 3, 2 * w // 3), (2 * w // 3, w))
            )

        ng, nm = int(green.sum()), int(magenta.sum())
        if ng > 25 and ng > 2 * nm and spread(green) >= 2:
            return True
        if nm > 25 and nm > 2 * ng and spread(magenta) >= 2:
            return False
        return None

    def _terminal_frame(self, ctx: dict) -> dict:
        # Contract (wayfinder 06): game-over detection takes priority over
        # diffs; the death turn skips r_dmg. Terminal reward is latched.
        if self._terminal_issued:
            # Defensive: the env guards _episode_over, so this is unreachable
            # in normal flow. Never double-pay the terminal reward.
            return self._frame_result(0.0, True, False, "already-terminated", {"terminal": 0.0}, ctx)
        victory = self._detect_victory(ctx.get("shot"))
        reward = R_VICTORY if victory else R_DEATH
        self._terminal_issued = True
        bd = {"terminal": reward, "victory": victory}
        return self._frame_result(
            reward, True, False, ctx.get("end_reason") or "gameover", bd, ctx
        )

    def _frame_result(
        self,
        reward: float,
        terminated: bool,
        truncated: bool,
        reason: str | None,
        breakdown: dict,
        ctx: dict,
        tkind: str | None = None,
    ) -> dict:
        return {
            "reward": float(reward),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "reason": reason,
            "diag": {
                "reward_breakdown": breakdown,
                "truncated_kind": tkind or ctx.get("truncated_kind"),
                "dialog_seen": ctx.get("dialog_seen", False),
                "ocr_fail_streak": self._ocr_fail_streak,
            },
        }

    def on_frame(
        self, prev_hud: dict[str, dict], cur_hud: dict[str, dict], ctx: dict
    ) -> dict:
        """Atomic frame hook -> {reward, terminated, truncated, reason, diag}.

        Reward state (per-field baselines/gaps, ratchet, streaks, latch) is
        owned here; prev_hud is informational only. Merges reward and
        terminal/truncation decisions atomically to avoid latch-ordering
        hazards (ticket 07). An env-side truncation in ctx is preserved as-is.
        """
        if ctx.get("terminated"):
            return self._terminal_frame(ctx)

        cur = self._parse_hud(cur_hud)
        step_ok = all(cur[f][1] for f in FIVE)
        self._ocr_fail_streak = 0 if step_ok else self._ocr_fail_streak + 1

        def usable(field: str) -> bool:
            """Field may contribute a diff: certain now, certain before, no gap."""
            v, c = cur[field]
            return bool(
                c and v is not None and not self._fgap.get(field, False) and field in self._base
            )

        reward = 0.0
        bd: dict[str, float] = {}
        progressed = False

        # Depth ratchet: only new records pay (blocks stair farming).
        if usable("depth") and self._max_depth is not None:
            d = cur["depth"][0]
            assert d is not None
            if d > self._max_depth:
                gain = R_DEPTH_RECORD * (d - self._max_depth)
                reward += gain
                bd["depth"] = round(gain, 6)
                progressed = True
        # Level-up; xp diff ignored on level-up turns (reset would double-count).
        level_up = False
        if usable("level"):
            lv = cur["level"][0]
            assert lv is not None
            if lv > self._base["level"]:
                reward += R_LEVEL_UP
                bd["level"] = R_LEVEL_UP
                progressed = True
                level_up = True
        if not level_up and usable("xp") and usable("level"):
            # level usable and not level_up => level == base level (never decreases).
            x = cur["xp"][0]
            assert x is not None
            if x > self._base["xp"]:
                gain = R_XP_PER * (x - self._base["xp"])
                reward += gain
                bd["xp"] = round(gain, 6)
        # Damage only: healing is never rewarded.
        if usable("hp"):
            h = cur["hp"][0]
            assert h is not None
            if h < self._base["hp"]:
                loss = R_DMG_PER * (self._base["hp"] - h)
                reward -= loss
                bd["damage"] = round(-loss, 6)

        # Living cost: waiting is strictly negative, every dungeon step.
        reward -= R_STEP_PENALTY
        bd["step"] = -R_STEP_PENALTY

        # Per-field baseline updates (certain reads only); gap flags refresh.
        t_v, t_c = cur["turn"]
        for f in FIVE:
            v, c = cur[f]
            if c and v is not None:
                self._base[f] = v
                self._fgap[f] = False
            else:
                self._fgap[f] = True
        mh_v, mh_c = cur["max_hp"]
        if mh_c and mh_v is not None:
            self._base_max_hp = mh_v

        # Silent re-ratchet on recovery (no backfill); progress clock.
        d_v, d_c = cur["depth"]
        if d_c and d_v is not None and (self._max_depth is None or d_v > self._max_depth):
            self._max_depth = d_v
            progressed = True
        if progressed and t_c and t_v is not None:
            self._last_progress_turn = t_v
        # First-certain-turn init: budget/stagnation must survive a blind seed.
        if t_c and t_v is not None:
            if self._start_turn is None:
                self._start_turn = t_v
            if self._last_progress_turn is None:
                self._last_progress_turn = t_v

        # Truncations. An env-side truncation (fault) is preserved verbatim;
        # adapter kinds only apply when the env hasn't already ended the episode.
        # Priority among adapter kinds: budget > stagnation > ocr-fail.
        truncated = bool(ctx.get("truncated", False))
        tkind = ctx.get("truncated_kind")
        reason = ctx.get("end_reason") or ctx.get("fault")
        if not truncated:
            if (
                t_c
                and t_v is not None
                and self._start_turn is not None
                and t_v - self._start_turn >= TURN_BUDGET
            ):
                truncated, tkind = True, "budget"
                reason = f"turn budget {TURN_BUDGET} reached"
            elif (
                t_c
                and t_v is not None
                and self._last_progress_turn is not None
                and t_v - self._last_progress_turn >= STAGNATION_TURNS
            ):
                truncated, tkind = True, "stagnation"
                reason = f"no progress for {STAGNATION_TURNS} turns"
                reward -= R_STAGNATION_PENALTY
                bd["stagnation"] = -R_STAGNATION_PENALTY
            elif self._ocr_fail_streak >= OCR_FAIL_LIMIT:
                truncated, tkind = True, "ocr"
                reason = f"OCR failed {OCR_FAIL_LIMIT} consecutive steps"

        return self._frame_result(reward, False, truncated, reason, bd, ctx, tkind=tkind)


def make_adapter() -> RuggrogueAdapter:
    return RuggrogueAdapter()
