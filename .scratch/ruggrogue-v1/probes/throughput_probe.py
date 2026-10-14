"""Parallel-env throughput probe: measure steps/sec with N browser envs.

Each env owns one headless Chromium. Run AFTER ticket 07's smoke training
finishes (it holds most of the VM's RAM).
Usage: .venv/bin/python .scratch/ruggrogue-v1/probes/throughput_probe.py [--envs N] [--steps K]
"""

from __future__ import annotations

import argparse
import time

from stable_baselines3.common.vec_env import SubprocVecEnv

from rl_game_agent.envs import ENV_REGISTRY


def make_env():
    def _thunk():
        return ENV_REGISTRY["ruggrogue-v1"]()

    return _thunk


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--envs", type=int, default=4)
    ap.add_argument("--steps", type=int, default=40)
    args = ap.parse_args()

    print(f"launching {args.envs} envs ...", flush=True)
    t0 = time.time()
    venv = SubprocVecEnv([make_env() for _ in range(args.envs)])
    venv.reset()
    t_reset = time.time() - t0
    print(f"reset {args.envs} envs: {t_reset:.1f}s", flush=True)

    import numpy as np

    t1 = time.time()
    for _ in range(args.steps):
        actions = np.array([venv.action_space.sample() for _ in range(args.envs)])
        venv.step(actions)
    dt = time.time() - t1
    total = args.steps * args.envs
    print(f"{total} steps in {dt:.1f}s -> {total / dt:.2f} steps/s total "
          f"({total / dt / args.envs:.2f} per env)")
    venv.close()


if __name__ == "__main__":
    main()
