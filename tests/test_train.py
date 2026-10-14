"""Fast unit/integration tests for train.py assembly.

Uses a tiny synthetic env (no browser) so the suite runs in seconds.
The real-env smoke run is done separately via the CLI.
"""

import gymnasium
import numpy as np
import pytest

from rl_game_agent.train import (
    TrainingGuardCallback,
    _ExpandChannel,
    build_model,
    should_abort,
)


class TinyEnv(gymnasium.Env):
    observation_space = gymnasium.spaces.Box(0, 255, (84, 84), np.uint8)
    action_space = gymnasium.spaces.Discrete(2)

    def __init__(self, fault: bool = False):
        super().__init__()
        self._fault = fault

    def reset(self, **kwargs):
        return np.zeros((84, 84), np.uint8), {}

    def step(self, action):
        info = (
            {"truncated_kind": "fault", "end_reason": "ocr", "hud_certain": False}
            if self._fault
            else {"truncated_kind": None, "end_reason": "death", "hud_certain": True}
        )
        return np.zeros((84, 84), np.uint8), 1.0, False, True, info


CFG = {
    "abort": {
        "fault_rate": 0.20,
        "fault_window_episodes": 50,
        "ocr_uncertain_rate": 0.30,
        "wall_clock_hours": 72,
    }
}


def test_should_abort_fault_rate():
    assert should_abort(0.21, 0.0, 10.0, CFG) is not None
    assert should_abort(0.20, 0.0, 10.0, CFG) is None


def test_should_abort_ocr_uncertain():
    assert should_abort(0.0, 0.31, 10.0, CFG) is not None
    assert should_abort(0.0, 0.30, 10.0, CFG) is None


def test_should_abort_wall_clock():
    assert should_abort(0.0, 0.0, 73 * 3600, CFG) is not None
    assert should_abort(0.0, 0.0, 10.0, CFG) is None


def test_expand_channel_shape_dtype():
    env = _ExpandChannel(TinyEnv())
    assert env.observation_space.shape == (84, 84, 1)
    assert env.observation_space.dtype == np.uint8
    obs, _ = env.reset()
    assert obs.shape == (84, 84, 1) and obs.dtype == np.uint8


def _tiny_vec(fault: bool = False):
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv, VecTransposeImage

    vec = DummyVecEnv([lambda: Monitor(_ExpandChannel(TinyEnv(fault=fault)))])
    return VecTransposeImage(vec)


def test_checkpoint_callback_fires(tmp_path):
    from stable_baselines3.common.callbacks import CheckpointCallback

    vec = _tiny_vec()
    model = build_model(
        {"policy": "CnnPolicy", "hyperparams": {"n_steps": 32}, "seed": 0},
        vec,
        tmp_path,
    )
    cb = CheckpointCallback(
        save_freq=50, save_path=str(tmp_path / "checkpoints"), name_prefix="t"
    )
    model.learn(total_timesteps=120, callback=cb)
    assert (tmp_path / "checkpoints" / "t_100_steps.zip").exists()


def test_guard_aborts_on_fault_storm():
    vec = _tiny_vec(fault=True)
    model = build_model(
        {"policy": "CnnPolicy", "hyperparams": {"n_steps": 32}, "seed": 0},
        vec,
        __import__("pathlib").Path("/tmp"),
    )
    guard = TrainingGuardCallback(CFG)
    model.learn(total_timesteps=500, callback=guard)
    assert guard.abort_reason is not None
    assert "fault" in guard.abort_reason
    assert model.num_timesteps < 500


def test_guard_passes_clean_run():
    vec = _tiny_vec(fault=False)
    model = build_model(
        {"policy": "CnnPolicy", "hyperparams": {"n_steps": 32}, "seed": 0},
        vec,
        __import__("pathlib").Path("/tmp"),
    )
    guard = TrainingGuardCallback(CFG)
    model.learn(total_timesteps=96, callback=guard)
    assert guard.abort_reason is None
    assert guard.outcome_summary().get("death", 0) > 0
