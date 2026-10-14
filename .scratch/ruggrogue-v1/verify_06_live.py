"""Live verification for ticket 06: one short real episode, print reward trace.

Requires: game server on :8901, playwright chromium installed.
Run: ~/workspace/rl-game-agent/.venv/bin/python verify_06_live.py
"""

from rl_game_agent.envs.browser_env import BrowserGameEnv
from rl_game_agent.envs.ruggrogue import make_adapter

env = BrowserGameEnv(adapter=make_adapter(), headless=True)
try:
    obs, info = env.reset()
    print(f"reset ok: phase={info['phase']} turn={info['turn']} depth={info['depth']} "
          f"hud_certain={info['hud_certain']}")
    for i in range(8):
        obs, reward, terminated, truncated, info = env.step(8)  # wait
        bd = info.get("reward_breakdown", {})
        print(f"step {i}: reward={reward:+.4f} breakdown={bd} "
              f"turn={info['turn']} depth={info['depth']} "
              f"term={terminated} trunc={truncated} kind={info.get('truncated_kind')}")
        if terminated or truncated:
            print(f"episode ended: reason={info.get('end_reason')}")
            break
finally:
    env.close()
print("LIVE TEST DONE")
