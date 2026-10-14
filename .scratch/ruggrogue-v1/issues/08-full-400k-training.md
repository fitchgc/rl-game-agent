# 08: GPU 训练启动包（原 200k 本机训练，已改向）

**What to build:** 交付在用户本地 GPU 机器上可直接启动正式训练的完整启动包；本 VM 不再执行长训练，只做流程验证。

**Blocked by:** 07 (PPO 短程训练冒烟), 09 (实现统一 evaluate.py).

**Status:** ready-for-agent

> **方向变更（用户 2026-10-14 决策）**：本 VM 的目标改为"验证整个流程可行、无 bug"；实际训练在用户本地 GPU 机器上跑。因此本票不再执行 200k 步训练，改为交付可移植的训练启动包。

- [ ] `configs/ruggrogue_ppo_v1.yaml` 定稿为正式训练配置（total_timesteps 保持 200_000；以 1.0 step/s 计约 55.6h——注意瓶颈在浏览器交互而非网络更新，GPU 主要加速 PPO 更新部分，步进吞吐仍受浏览器限制）。
- [ ] 提供 GPU 机器环境准备脚本/说明：venv、torch CUDA 版、stable-baselines3、playwright + Chromium 安装、游戏文件按 `vendor/ruggrogue-web/MANIFEST.json` 获取与校验、静态服务启动。
- [ ] 提供启动/恢复/状态检查/安全停止命令（对应 train.py 的 --config/--timesteps/--out），以及 TensorBoard 查看说明。
- [ ] 在本 VM 做启动路径验证：用正式配置启动训练，确认首个 rollout + checkpoint 正常落盘后干净停止（不等跑完），证明启动包无 bug。
- [ ] 输出一份交接说明：需要用户在 GPU 机器上执行的确切命令序列、预期耗时、产物位置、以及 10k 步吞吐校准方法。

## Notes

- 07 号票（本 VM 短程冒烟）即为"流程可行性"的主验证；本票验证"启动包可移植"。
- 72h 墙钟中止线保留在配置说明中，供 GPU 机器参考。
