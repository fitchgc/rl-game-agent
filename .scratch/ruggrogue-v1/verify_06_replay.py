"""Replay verification for ticket 06: reward formula on synthetic HUD tapes.

No browser needed. Exercises RuggrogueAdapter.on_frame directly:
shaping diffs, terminal latch, truncations, OCR certainty policy, gates.
Run: ~/workspace/rl-game-agent/.venv/bin/python verify_06_replay.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "/home/hatch/workspace/rl-game-agent/src")

from PIL import Image, ImageDraw

from rl_game_agent.envs.ruggrogue import RuggrogueAdapter


def hud(depth, level, xp, hp, max_hp, turn, certain=True):
    def f(v):
        return {"value": str(v), "certain": certain}

    return {
        "Depth": f(depth),
        "Level": f(level),
        "Experience": f(xp),
        "Health": {"value": f"{hp}/{max_hp}", "certain": certain},
        "Turn": f(turn),
    }


def gameover_shot(color):
    """Synthetic game-over screen: colored title strip on black."""
    img = Image.new("RGB", (1280, 800), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 40], fill=color)
    return img


GREEN = (0, 220, 0)
MAGENTA = (220, 0, 220)

passed = []


def check(name, cond, extra=""):
    assert cond, f"FAIL: {name} {extra}"
    passed.append(name)
    print(f"  ok: {name}" + (f" ({extra})" if extra else ""))


def fresh():
    a = RuggrogueAdapter()
    a.seed_baselines(hud(1, 1, 0, 30, 30, 1))
    return a


print("== shaping diffs ==")
a = fresh()
r = a.on_frame(hud(1, 1, 0, 30, 30, 1), hud(1, 1, 0, 30, 30, 2), {})
check("wait step = -0.001", abs(r["reward"] + 0.001) < 1e-9, f"got {r['reward']}")
check("breakdown has step", r["diag"]["reward_breakdown"].get("step") == -0.001)

r = a.on_frame(hud(1, 1, 0, 30, 30, 2), hud(1, 1, 5, 30, 30, 3), {})
check("xp gain = 0.001*5 - 0.001", abs(r["reward"] - 0.004) < 1e-9, f"got {r['reward']}")

r = a.on_frame(hud(1, 1, 5, 30, 30, 3), hud(1, 1, 5, 25, 30, 4), {})
check("damage 5 = -0.05 - 0.001", abs(r["reward"] + 0.051) < 1e-9, f"got {r['reward']}")
check("damage breakdown", r["diag"]["reward_breakdown"].get("damage") == -0.05)

r = a.on_frame(hud(1, 1, 5, 25, 30, 4), hud(1, 1, 5, 30, 30, 5), {})
check("heal gives no reward", abs(r["reward"] + 0.001) < 1e-9, f"got {r['reward']}")

r = a.on_frame(hud(1, 1, 5, 30, 30, 5), hud(1, 2, 0, 30, 32, 6), {})
check("level-up = 0.5 - 0.001 (xp reset ignored)", abs(r["reward"] - 0.499) < 1e-9, f"got {r['reward']}")

r = a.on_frame(hud(1, 2, 0, 30, 32, 6), hud(2, 2, 0, 30, 32, 6), {})
check("new depth record = 1.0 - 0.001", abs(r["reward"] - 0.999) < 1e-9, f"got {r['reward']}")

r = a.on_frame(hud(2, 2, 0, 30, 32, 6), hud(1, 2, 0, 30, 32, 7), {})
check("ascending pays 0 (no stair farm)", abs(r["reward"] + 0.001) < 1e-9, f"got {r['reward']}")

print("== terminal ==")
a = fresh()
r = a.on_frame(hud(3, 2, 9, 0, 30, 40), hud(3, 2, 9, 0, 30, 40),
               {"terminated": True, "shot": gameover_shot(MAGENTA)})
check("death = -1.0, terminated", r["reward"] == -1.0 and r["terminated"] is True)
r2 = a.on_frame(hud(3, 2, 9, 0, 30, 40), hud(3, 2, 9, 0, 30, 40),
                {"terminated": True, "shot": gameover_shot(MAGENTA)})
check("terminal latch: no double pay", r2["reward"] == 0.0 and r2["reason"] == "already-terminated")

a = fresh()
r = a.on_frame(hud(5, 4, 20, 18, 34, 900), hud(5, 4, 20, 18, 34, 900),
               {"terminated": True, "shot": gameover_shot(GREEN)})
check("victory = +10.0", r["reward"] == 10.0 and r["terminated"] is True,
      f"got {r['reward']}")

print("== truncations ==")
a = fresh()
r = a.on_frame(hud(9, 9, 99, 40, 40, 4999), hud(9, 9, 99, 40, 40, 5001), {})
check("5000-turn budget truncates", r["truncated"] is True
      and r["diag"]["truncated_kind"] == "budget", f"got {r['diag']['truncated_kind']}")

a = fresh()  # start turn=1, progress at turn=1
r = a.on_frame(hud(1, 1, 0, 30, 30, 300), hud(1, 1, 0, 30, 30, 301), {})
check("300-turn stagnation truncates with -0.5",
      r["truncated"] is True and r["diag"]["truncated_kind"] == "stagnation"
      and abs(r["reward"] + 0.501) < 1e-9, f"got {r['reward']} {r['diag']['truncated_kind']}")

a = fresh()
last = None
for _ in range(20):
    bad = hud(1, 1, 0, 30, 30, 2, certain=False)
    last = a.on_frame(bad, bad, {})
check("20 OCR failures truncate (ocr kind)",
      last["truncated"] is True and last["diag"]["truncated_kind"] == "ocr")
check("uncertain steps pay no diff reward",
      abs(last["reward"] + 0.001) < 1e-9, f"got {last['reward']}")

print("== uncertainty policy ==")
a = fresh()
a.on_frame(hud(1, 1, 0, 30, 30, 1), hud(1, 1, 0, 30, 30, 2, certain=False), {})
check("gap flags set after uncertain",
      all(a._fgap.get(f) for f in ("depth", "level", "xp", "hp", "turn")))
r = a.on_frame(hud(1, 1, 0, 30, 30, 2), hud(3, 1, 0, 30, 30, 4), {})
check("recovery: no backfill for missed depth 1->3",
      abs(r["reward"] + 0.001) < 1e-9, f"got {r['reward']}")
check("recovery: max_depth re-based to 3", a._max_depth == 3)
r = a.on_frame(hud(3, 1, 0, 30, 30, 4), hud(3, 1, 0, 30, 30, 5), {})
check("post-recovery normal", abs(r["reward"] + 0.001) < 1e-9)

a = fresh()
r = a.on_frame(hud(1, 1, 0, 30, 30, 1), hud(1, 1, 0, 99, 30, 2), {})
check("hp>max_hp gate demotes to uncertain", a._fgap.get("hp") is True
      and abs(r["reward"] + 0.001) < 1e-9)

a = fresh()
r = a.on_frame(hud(1, 1, 0, 30, 30, 1), hud(5, 1, 0, 30, 30, 2), {})
check("|ddepth|>1 gate demotes to uncertain", a._fgap.get("depth") is True)

a = RuggrogueAdapter()
a.seed_baselines(hud(1, 2, 0, 30, 30, 1))  # base level = 2
r = a.on_frame(hud(1, 2, 0, 30, 30, 1), hud(1, 1, 0, 30, 30, 2), {})
check("level decrease gate demotes to uncertain", a._fgap.get("level") is True)

print("== per-field independence (red-team #3) ==")
a = fresh()
# HP drops 30->25 (certain) while XP read fails: damage must still be punished.
bad_xp = hud(1, 1, 10, 30, 30, 2)
bad_xp["Experience"] = {"value": "?", "certain": False}
r = a.on_frame(hud(1, 1, 10, 30, 30, 1), {"Depth": {"value": "1", "certain": True},
    "Level": {"value": "1", "certain": True}, "Experience": bad_xp["Experience"],
    "Health": {"value": "25/30", "certain": True}, "Turn": {"value": "2", "certain": True}}, {})
check("hp diff flows despite xp uncertain",
      abs(r["reward"] + 0.051) < 1e-9, f"got {r['reward']}")
check("hp baseline updated despite xp gap", a._base["hp"] == 25)
r = a.on_frame(hud(1, 1, 10, 25, 30, 2), hud(1, 1, 10, 25, 30, 3), {})
check("no double-punish next step", abs(r["reward"] + 0.001) < 1e-9, f"got {r['reward']}")

print("== poisoning resistance (red-team #1) ==")
a = fresh()
for t in (2, 3, 4):
    bad = hud(99, 1, 0, 30, 30, t)
    a.on_frame(hud(1, 1, 0, 30, 30, t - 1), bad, {})
check("repeated depth=99 misreads never poison max_depth", a._max_depth == 1)
check("depth stays gapped", a._fgap.get("depth") is True)

print("== blind-seed recovery (red-team #2) ==")
a = RuggrogueAdapter()
blind = hud(1, 1, 0, 30, 30, 1)
blind["Turn"] = {"value": "?", "certain": False}
a.seed_baselines(blind)
check("blind seed: no start turn yet", a._start_turn is None)
r = a.on_frame(blind, hud(1, 1, 0, 30, 30, 100), {})
check("first certain turn initializes budget clock", a._start_turn == 100)
check("... and progress clock", a._last_progress_turn == 100)

print("== env-side truncation passthrough (red-team #5) ==")
a = fresh()
r = a.on_frame(hud(1, 1, 0, 30, 30, 1), hud(1, 1, 0, 30, 30, 2),
               {"truncated": True, "truncated_kind": "fault", "fault": "sync timeout"})
check("ctx truncated preserved", r["truncated"] is True)
check("ctx kind preserved", r["diag"]["truncated_kind"] == "fault")
check("ctx reason preserved", r["reason"] == "sync timeout")

print("== victory false-positive guard (red-team #6) ==")
a = fresh()
blob = Image.new("RGB", (1280, 800), (0, 0, 0))
d = ImageDraw.Draw(blob)
d.rectangle([0, 0, 10, 10], fill=(0, 220, 0))  # small stray green blob, one third
r = a.on_frame(hud(1, 1, 0, 0, 30, 50), hud(1, 1, 0, 0, 30, 50),
               {"terminated": True, "shot": blob})
check("stray green blob does not false-positive to victory",
      r["reward"] == -1.0, f"got {r['reward']}")

print(f"\nALL {len(passed)} REPLAY CHECKS PASSED")
