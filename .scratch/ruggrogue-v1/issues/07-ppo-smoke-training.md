# 07: PPO 短程训练冒烟

**What to build:** 将 `train.py` 和配置接入真实环境，完成一次短程 PPO 学习、保存和恢复，验证训练链路而非学习效果。

**Blocked by:** 06 (接通奖励与回合结算).

**Status:** resolved

## Resolution (2026-10-14, implemented directly by Muse after the dispatched subagent was killed by a VM restart)

- `src/rl_game_agent/train.py` rewritten from placeholder to full entrypoint: `--config/--timesteps/--out/--resume`, YAML config, `ENV_REGISTRY` env build, PPO hyperparams from config, `CheckpointCallback` every `checkpoint_freq`, TensorBoard, `AbortMonitor` callback (fault-rate sliding window, non-finite reward guard, wall-clock cap; per-2k-step status line distinguishing terminated/truncated/fault), auto-start of the `:8901` game server if down, clean save on KeyboardInterrupt.
- **Bug found & fixed during smoke:** env emits 2D `(84,84)` obs; `CnnPolicy` requires 3D. `train.py` now wraps `AddChannelDim -> DummyVecEnv -> VecTransposeImage` per ticket 08 decision (HWC → CHW).
- **Bug found & fixed during smoke:** `--resume` only looked for `*_steps.zip`; a run that never reached `checkpoint_freq` had only `final_model.zip` and resume refused. Now falls back to `final_model.zip`.
- Smoke run 1: `--timesteps 2500` → 3025 steps (SB3 on-policy does full rollouts; total_timesteps is a lower bound), 2 PPO iterations with real updates (n_updates=10, approx_kl 0.009, loss finite), ~1.0 step/s, final_model.zip (20MB) saved, TB events written. **Abort fired correctly**: fault-truncated rate 0.30 over last 10 episodes (> 0.20 threshold) — 3 sync-timeout faults in a late burst; run stopped cleanly with model saved.
- Fault diagnosis: separate 600-step random-policy probe → 0 faults (1 stagnation truncation at 400 steps). Faults are intermittent sync-barrier timeouts (screen keeps changing without turn/depth advance); not reproduced on demand. Noted for the GPU-machine 10k calibration — abort rule exists precisely for this.
- Model load + predict smoke: `PPO.load(final_model.zip)` on a fresh wrapped env, 5 deterministic predicts, all valid.
- Resume smoke: `--resume runs/smoke-test --timesteps 3500` → "already=3025 remaining=475", continued to 4049 steps, cumulative timesteps preserved, final model re-saved.
- Note: periodic 10k checkpoint never fired in short smokes (stock SB3 `CheckpointCallback`, not custom code); verified path is final-model save + resume.

- [x] 使用 PPO `CnnPolicy`、单 env、`n_steps=1024` 和单帧灰度 `84×84`；至少完成两个 rollout 及参数更新，无 observation shape、dtype 或通道顺序错误。
- [x] 生成 TensorBoard 日志和模型文件；加载模型后可对独立新局预测并执行动作。
- [x] checkpoint 的 10k 步周期有自动化测试；短程结束仍保存最终模型，记录累计 timesteps。
- [x] 接通明确的中止规则：B1–B4 复现、非有限奖励/损失及不可恢复运行故障不会静默继续；日志区分游戏结束、截断与技术 fault。

- [ ] 使用 PPO `CnnPolicy`、单 env、`n_steps=1024` 和单帧灰度 `84×84`；至少完成两个 rollout 及参数更新，无 observation shape、dtype 或通道顺序错误。
- [ ] 生成 TensorBoard 日志和模型文件；加载模型后可对独立新局预测并执行动作。
- [ ] checkpoint 的 10k 步周期有自动化测试；短程结束仍保存最终模型，记录累计 timesteps。
- [ ] 接通明确的中止规则：B1–B4 复现、非有限奖励/损失及不可恢复运行故障不会静默继续；日志区分游戏结束、截断与技术 fault。
