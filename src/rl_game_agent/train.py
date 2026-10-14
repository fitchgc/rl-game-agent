"""Training entrypoint: train an SB3 agent on a registered game environment.

Assembly per wayfinder ticket 08: ENV_REGISTRY factory -> channel-expand
(84,84)->(84,84,1) -> Monitor -> DummyVecEnv -> VecTransposeImage -> PPO.
All numbers live in the config file; this module only assembles.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter, deque
from pathlib import Path

import gymnasium
import numpy as np
import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecTransposeImage

from .envs import ENV_REGISTRY

log = logging.getLogger("rl_game_agent.train")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_config(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------- #
# Env assembly
# --------------------------------------------------------------------------- #
class _ExpandChannel(gymnasium.Wrapper):
    """(84, 84) uint8 -> (84, 84, 1) uint8 so SB3 sees HWC image space.

    The adapter's contract keeps frame_shape at (84, 84) (ticket 07); the
    HWC->CHW transpose ticket 08 assigns to train.py lives here, before
    VecTransposeImage.
    """

    def __init__(self, env: gymnasium.Env) -> None:
        super().__init__(env)
        h, w = env.observation_space.shape
        self.observation_space = gymnasium.spaces.Box(
            low=0, high=255, shape=(h, w, 1), dtype=np.uint8
        )

    def reset(self, **kwargs):
        obs, info = self.env.reset(**kwargs)
        return np.expand_dims(obs, -1), info

    def step(self, action):
        obs, reward, terminated, truncated, info = self.env.step(action)
        return np.expand_dims(obs, -1), reward, terminated, truncated, info


def build_env(env_name: str, seed: int):
    """Single env: factory -> channel expand -> Monitor -> DummyVecEnv -> transpose."""
    if env_name not in ENV_REGISTRY:
        raise KeyError(f"unknown env {env_name!r}; registered: {sorted(ENV_REGISTRY)}")

    def _make():
        return Monitor(_ExpandChannel(ENV_REGISTRY[env_name]()))

    vec = DummyVecEnv([_make])
    vec.seed(seed)
    vec = VecTransposeImage(vec)
    vec.reset()
    return vec


# --------------------------------------------------------------------------- #
# Abort rules (ticket 08) - pure decision function, unit-tested
# --------------------------------------------------------------------------- #
def should_abort(
    fault_rate: float,
    ocr_uncertain_rate: float,
    elapsed_s: float,
    cfg: dict,
) -> str | None:
    """Return an abort reason, or None to continue training."""
    abort = cfg.get("abort", {}) or {}
    if fault_rate > float(abort.get("fault_rate", 0.20)):
        return f"fault truncated rate {fault_rate:.2%} exceeds limit"
    if ocr_uncertain_rate > float(abort.get("ocr_uncertain_rate", 0.30)):
        return f"OCR uncertain rate {ocr_uncertain_rate:.2%} exceeds limit"
    cap_h = float(abort.get("wall_clock_hours", 72))
    if elapsed_s > cap_h * 3600:
        return f"wall-clock cap {cap_h}h reached (safe stop, no reward fabrication)"
    return None


class TrainingGuardCallback(BaseCallback):
    """Enforces abort rules and logs terminated/truncated/fault distinctly.

    Sliding window over finished episodes; reads the adapter's info keys
    (end_reason, truncated_kind, hud_certain). Returning False stops
    model.learn() cleanly.
    """

    def __init__(self, cfg: dict, verbose: int = 0) -> None:
        super().__init__(verbose)
        abort = cfg.get("abort", {}) or {}
        self._window = int(abort.get("fault_window_episodes", 50))
        self._episodes: deque[dict] = deque(maxlen=self._window)
        self._cfg = cfg
        self._t0 = time.time()
        self._outcome_counts: Counter = Counter()
        self.abort_reason: str | None = None

    def _on_step(self) -> bool:
        # Non-finite reward: never silently continue.
        rewards = self.locals.get("rewards")
        if rewards is not None and not np.all(np.isfinite(rewards)):
            self.abort_reason = "non-finite reward detected"
            log.critical("ABORT: %s", self.abort_reason)
            return False

        infos = self.locals.get("infos", [])
        for info in infos:
            ep = info.get("episode")
            if ep is None:
                continue  # Monitor only adds this at episode end
            outcome = {
                "end_reason": info.get("end_reason", "?"),
                "truncated_kind": info.get("truncated_kind"),
                "hud_certain": info.get("hud_certain", True),
            }
            self._episodes.append(outcome)
            kind = outcome["truncated_kind"] or outcome["end_reason"]
            self._outcome_counts[kind] += 1
            log.info(
                "episode done: end_reason=%s truncated_kind=%s reward=%.2f len=%d",
                outcome["end_reason"],
                outcome["truncated_kind"],
                ep["r"],
                ep["l"],
            )

        if self._episodes:
            n = len(self._episodes)
            fault_rate = sum(
                1 for e in self._episodes if e["truncated_kind"] == "fault"
            ) / n
            ocr_uncertain_rate = sum(
                1 for e in self._episodes if not e["hud_certain"]
            ) / n
            reason = should_abort(
                fault_rate, ocr_uncertain_rate, time.time() - self._t0, self._cfg
            )
            if reason is not None:
                self.abort_reason = reason
                log.critical("ABORT: %s", reason)
                return False
        return True

    def outcome_summary(self) -> dict:
        return dict(self._outcome_counts)


# --------------------------------------------------------------------------- #
# Model assembly
# --------------------------------------------------------------------------- #
def build_model(cfg: dict, vec_env, out_dir: Path, resume_path: str | None = None):
    hyper = dict(cfg.get("hyperparams", {}))
    tb_log = str(out_dir / "tb") if cfg.get("tensorboard") else None
    if resume_path:
        log.info("resuming from %s", resume_path)
        model = PPO.load(resume_path, env=vec_env, tensorboard_log=tb_log)
        # Refresh hyperparams that are safe to override post-load.
        return model
    return PPO(
        cfg.get("policy", "CnnPolicy"),
        vec_env,
        verbose=1,
        seed=int(cfg.get("seed", 0)),
        tensorboard_log=tb_log,
        **hyper,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(description="Train an RL agent to play a game.")
    parser.add_argument("--config", default="configs/ruggrogue_ppo_v1.yaml")
    parser.add_argument("--timesteps", type=int, default=None,
                        help="Override total timesteps (smoke tests).")
    parser.add_argument("--out", default="models")
    parser.add_argument("--resume", default=None, help="Path to a .zip checkpoint to resume from.")
    parser.add_argument("--seed", type=int, default=None, help="Override config seed.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    total = args.timesteps if args.timesteps is not None else int(cfg["total_timesteps"])
    if args.seed is not None:
        cfg["seed"] = args.seed
    out = Path(args.out)
    (out / "checkpoints").mkdir(parents=True, exist_ok=True)

    log.info("config=%s algo=%s env=%s policy=%s total_timesteps=%d",
             args.config, cfg["algo"], cfg["env"], cfg.get("policy"), total)

    vec_env = build_env(cfg["env"], int(cfg.get("seed", 0)))
    log.info("obs space after transpose: %s", vec_env.observation_space)

    model = build_model(cfg, vec_env, out, args.resume)
    remaining = total - model.num_timesteps
    if remaining <= 0:
        log.info("already at %d timesteps >= target %d; nothing to do",
                 model.num_timesteps, total)
        return

    checkpoint_cb = CheckpointCallback(
        save_freq=int(cfg.get("checkpoint_freq", 10_000)),
        save_path=str(out / "checkpoints"),
        name_prefix="ruggrogue_ppo",
    )
    guard_cb = TrainingGuardCallback(cfg)

    # B1-B4 surface as RuntimeError from the env: log loudly, never swallow.
    try:
        model.learn(total_timesteps=remaining, callback=[checkpoint_cb, guard_cb])
    except RuntimeError as exc:
        log.critical("ABORT: unrecoverable env failure: %s", exc)
        sys.exit(2)

    final_path = out / "final_model.zip"
    model.save(str(final_path))
    log.info("saved %s timesteps=%d outcomes=%s abort_reason=%s",
             final_path, model.num_timesteps, guard_cb.outcome_summary(),
             guard_cb.abort_reason)
    if guard_cb.abort_reason:
        sys.exit(3)


if __name__ == "__main__":
    main()
