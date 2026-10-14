"""Diagnose fault-truncated episodes under a random policy.

Prints each episode's length, end reason and truncated_kind.
Usage: .venv/bin/python .scratch/ruggrogue-v1/probes/fault_diagnose.py [--steps 600]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def ensure_server() -> None:
    try:
        urllib.request.urlopen("http://localhost:8901/index.html", timeout=3)
        return
    except OSError:
        pass
    repo = Path(__file__).resolve().parents[3]
    subprocess.Popen(
        [sys.executable, "-m", "http.server", "8901",
         "--directory", str(repo / "vendor" / "ruggrogue-web")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(0.5)
        try:
            urllib.request.urlopen("http://localhost:8901/index.html", timeout=3)
            return
        except OSError:
            continue
    raise RuntimeError("game server did not come up")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=600)
    args = ap.parse_args()

    ensure_server()
    from rl_game_agent.envs import ENV_REGISTRY

    env = ENV_REGISTRY["ruggrogue-v1"]()
    ep = 0
    ep_len = 0
    for i in range(args.steps):
        if ep_len == 0:
            env.reset()
        _, _, terminated, truncated, info = env.step(env.action_space.sample())
        ep_len += 1
        if terminated or truncated:
            ep += 1
            print(
                f"ep={ep} len={ep_len} term={terminated} trunc={truncated} "
                f"kind={info.get('truncated_kind')} reason={info.get('end_reason')}",
                flush=True,
            )
            ep_len = 0
    env.close()
    print("done", flush=True)


if __name__ == "__main__":
    main()
