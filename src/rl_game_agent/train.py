"""Training entrypoint: train an SB3 agent on a registered browser game env.

Usage:
    .venv/bin/python -m rl_game_agent.train --config configs/ruggrogue_ppo_v1.yaml
    .venv/bin/python -m rl_game_agent.train --config ... --timesteps 5000 --out runs/smoke
    .venv/bin/python -m rl_game_agent.train --config ... --resume runs/smoke  # continue
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import yaml
from gymnasium import ObservationWrapper, spaces
from stable_baselines3 import PPO
from stable_baselines3.common.base_class import BaseAlgorithm
from stable_baselines3.common.callbacks import (
    BaseCallback,
    CheckpointCallback,
)
from stable_baselines3.common.logger import configure
from stable_baselines3.common.vec_env import DummyVecEnv, VecTransposeImage

from rl_game_agent.envs import ENV_REGISTRY


class AddChannelDim(ObservationWrapper):
    """(H, W) grayscale -> (H, W, 1): what ticket 08 specified (HWC)."""

    def __init__(self, env):
        super().__init__(env)
        h, w = env.observation_space.shape
        self.observation_space = spaces.Box(0, 255, (h, w, 1), np.uint8)

    def observation(self, obs):
        return np.expand_dims(obs, -1)

GAME_URL = "http://localhost:8901/index.html"


def ensure_game_server(web_dir: Path) -> None:
    """Make sure the static game server answers; start it if not."""
    try:
        urllib.request.urlopen(GAME_URL, timeout=3)
        return
    except OSError:
        pass
    subprocess.Popen(
        [sys.executable, "-m", "http.server", "8901", "--directory", str(web_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(GAME_URL, timeout=3)
            return
        except OSError:
            continue
    raise RuntimeError("game server did not come up on :8901")


class AbortMonitor(BaseCallback):
    """Enforce abort rules from the training config.

    Tracks fault-truncated episode rate over a sliding window, non-finite
    rewards, and a wall-clock cap. Logs terminated/truncated/fault counts
    distinctly so a stop is never silent about its cause.
    """

    def __init__(self, abort_cfg: dict, verbose: int = 0):
        super().__init__(verbose)
        self.cfg = abort_cfg or {}
        self.t0 = time.time()
        self.fault_window: list[bool] = []
        self.window = int(self.cfg.get("fault_window_episodes", 50))
        self.min_eps = int(self.cfg.get("min_episodes", 10))
        self.n_episodes = 0
        self.n_fault = 0
        self.n_truncated = 0
        self.n_terminated = 0

    def _on_step(self) -> bool:
        for info in self.locals.get("infos", []):
            if info.get("terminal_observation") is None and not info.get("TimeLimit.truncated"):
                continue
            # One episode ended on this env.
            self.n_episodes += 1
            kind = info.get("truncated_kind")  # None for terminated (win/death)
            is_fault = kind in ("fault", "ocr")
            self.fault_window.append(is_fault)
            self.fault_window = self.fault_window[-self.window :]
            self.n_fault += is_fault
            if kind:
                self.n_truncated += 1
            else:
                self.n_terminated += 1
        # Non-finite reward guard.
        rewards = self.locals.get("rewards")
        if rewards is not None:
            import numpy as np

            if not np.all(np.isfinite(rewards)):
                print("ABORT: non-finite reward detected", flush=True)
                return False
        # Fault-rate abort.
        if len(self.fault_window) >= self.min_eps:
            rate = sum(self.fault_window) / len(self.fault_window)
            if rate > float(self.cfg.get("fault_rate", 0.20)):
                print(
                    f"ABORT: fault-truncated episode rate {rate:.2f} "
                    f"over last {len(self.fault_window)} episodes",
                    flush=True,
                )
                return False
        # Wall-clock abort.
        cap_h = float(self.cfg.get("wall_clock_hours", 72))
        if (time.time() - self.t0) > cap_h * 3600:
            print(f"ABORT: wall-clock cap {cap_h}h reached", flush=True)
            return False
        # Periodic status line (every ~2k steps).
        if self.num_timesteps % 2000 == 0:
            el = (time.time() - self.t0) / 3600
            print(
                f"[t+{el:.2f}h] steps={self.num_timesteps} "
                f"ep={self.n_episodes} term={self.n_terminated} "
                f"trunc={self.n_truncated} fault={self.n_fault}",
                flush=True,
            )
        return True


def find_latest_checkpoint(out: Path) -> Path | None:
    ckpts = sorted(out.glob("*_steps.zip"))
    if ckpts:
        return ckpts[-1]
    final = out / "final_model.zip"
    return final if final.is_file() else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Train an SB3 agent on a browser game.")
    ap.add_argument("--config", default="configs/ruggrogue_ppo_v1.yaml")
    ap.add_argument("--timesteps", type=int, default=None)
    ap.add_argument("--out", default="runs/ruggrogue-v1")
    ap.add_argument("--resume", default=None, help="run dir to resume from")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    total = args.timesteps or int(cfg["total_timesteps"])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Game files must be served before the env boots its browser.
    repo_root = Path(__file__).resolve().parents[3]
    ensure_game_server(repo_root / "vendor" / "ruggrogue-web")

    env_name = cfg["env"]
    if env_name not in ENV_REGISTRY:
        raise SystemExit(f"unknown env {env_name!r}; registered: {list(ENV_REGISTRY)}")
    # Ticket 08: grayscale 84x84 uint8 HWC -> VecTransposeImage -> CHW for CnnPolicy.
    env = VecTransposeImage(DummyVecEnv([lambda: AddChannelDim(ENV_REGISTRY[env_name]())]))
    print(f"env={env_name} obs={env.observation_space} act={env.action_space}", flush=True)

    hp = cfg.get("hyperparams", {})
    tensorboard_log = str(out / "tb") if cfg.get("tensorboard") else None

    resume_from = None
    if args.resume:
        resume_from = find_latest_checkpoint(Path(args.resume))
        if resume_from is None:
            raise SystemExit(f"no checkpoint found in {args.resume}")

    if resume_from:
        print(f"resuming from {resume_from}", flush=True)
        model: BaseAlgorithm = PPO.load(
            resume_from, env=env, tensorboard_log=tensorboard_log
        )
        # Continue counting from the checkpoint's step.
        already = model.num_timesteps
        remaining = max(0, total - already)
        print(f"already={already} remaining={remaining}", flush=True)
    else:
        model = PPO(
            cfg.get("policy", "CnnPolicy"),
            env,
            learning_rate=hp.get("learning_rate", 3e-4),
            n_steps=hp.get("n_steps", 1024),
            batch_size=hp.get("batch_size", 64),
            n_epochs=hp.get("n_epochs", 10),
            gamma=hp.get("gamma", 0.99),
            gae_lambda=hp.get("gae_lambda", 0.95),
            clip_range=hp.get("clip_range", 0.2),
            ent_coef=hp.get("ent_coef", 0.0),
            seed=cfg.get("seed", 0),
            tensorboard_log=tensorboard_log,
            verbose=1,
        )
        remaining = total

    if tensorboard_log:
        configure(tensorboard_log, ["tensorboard"])

    callbacks = [
        CheckpointCallback(
            save_freq=int(cfg.get("checkpoint_freq", 10_000)),
            save_path=str(out / "checkpoints"),
            name_prefix="ppo_ruggrogue",
        ),
        AbortMonitor(cfg.get("abort", {})),
    ]
    try:
        model.learn(total_timesteps=remaining, callback=callbacks, reset_num_timesteps=False)
    except KeyboardInterrupt:
        print("interrupted by user; saving ...", flush=True)
    finally:
        model.save(out / "final_model")
        print(f"saved final model to {out / 'final_model.zip'}", flush=True)
        env.close()


if __name__ == "__main__":
    main()
