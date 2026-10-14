# GPU 训练交接说明（ruggrogue v1 / PPO）

本 VM 只做流程验证；正式训练在这台 GPU 机器上跑。本文是从零到训练完成的完整操作序列。

## 0. 前提

- 一台有 NVIDIA GPU 的 Linux 机器，Python ≥ 3.10，git，已装 NVIDIA 驱动
- 本仓库已 clone（`vendor/`、`runs/` 等大文件不在 git 里，由 setup 脚本获取）

## 1. 环境准备（一键）

```bash
bash scripts/setup_training_env.sh
```

脚本会做（可重复执行）：
1. 建 `.venv`，升级 pip
2. 装 CUDA 版 torch（默认 cu126；不同 CUDA 版本用 `TORCH_INDEX_URL=... bash scripts/setup_training_env.sh`，地址见 https://pytorch.org/get-started/locally/）
3. `pip install -e .` 装项目依赖
4. `playwright install chromium`
5. 从官网 `https://tung.github.io/ruggrogue/play/` 拉游戏文件到 `vendor/ruggrogue-web/`，逐文件 sha256 校验（不匹配直接报错退出）
6. 启动 `:8901` 静态服务

验证：

```bash
.venv/bin/python -c "import torch; print(torch.__version__, torch.cuda.is_available())"  # 期待 True
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8901/index.html               # 期待 200
```

## 2. 10k 步吞吐校准（正式训练前必做）

```bash
.venv/bin/python -m rl_game_agent.train \
  --config configs/ruggrogue_ppo_v1.yaml \
  --timesteps 10000 --out runs/calibration
```

记录终端打印的 `fps`（≈ 每秒步数）。再测并行（从 4 起）：

```bash
# 临时把 configs/ruggrogue_ppo_v1.yaml 里 num_envs 改成 4，再跑一次 10k
```

按实测 fps 决定正式训练的 `num_envs`（建议取"再加 env 几乎不涨总吞吐"之前的那个值）。
200k 步耗时 ≈ 200000 / fps / 3600 小时。本 VM 实测供参考：1 env ~1.0 step/s，
2 env 1.78 step/s，4 env 2.11 step/s（2 核饱和；核数多应接近线性）。

注意两点：
- 瓶颈在浏览器交互，GPU 加速的是 PPO 网络更新，不是步进
- SB3 on-policy 按整 rollout 跑，`total_timesteps` 是下界（设 2500 实际跑到 3025）

## 3. 启动正式训练

```bash
nohup .venv/bin/python -m rl_game_agent.train \
  --config configs/ruggrogue_ppo_v1.yaml \
  --out runs/ruggrogue-v1-full > runs/ruggrogue-v1-full/train.log 2>&1 &
```

关键行为（已在本 VM 验证）：
- 每 `checkpoint_freq`（默认 10k）步在 `runs/<out>/checkpoints/` 存 `ppo_ruggrogue_<steps>_steps.zip`
- TensorBoard 日志在 `runs/<out>/tb/`，看：`.venv/bin/tensorboard --logdir runs/ruggrogue-v1-full/tb`
- 结束（或 Ctrl-C / abort 触发）时存 `runs/<out>/final_model.zip`
- 状态行每 ~2k 步打印一次：`[t+xxh] steps=.. ep=.. term=.. trunc=.. fault=..`

## 4. 监控与中止规则

`configs/ruggrogue_ppo_v1.yaml` 的 `abort` 段（已验证会正确触发）：
- 滑动窗口（默认 50 局，至少 10 局）内 fault 截断率 > 0.20 → 干净停机并保存模型
- 非有限 reward → 停机
- 墙钟超过 72h → 停机

**重点观察**：冒烟时曾出现 3 次 sync-timeout fault 的小 burst（另一次 600 步诊断 0 fault，
间歇性）。如果校准阶段 fault 率持续偏高，先停下来排查，不要硬跑。

## 5. 恢复训练

```bash
.venv/bin/python -m rl_game_agent.train \
  --config configs/ruggrogue_ppo_v1.yaml \
  --out runs/ruggrogue-v1-full --resume runs/ruggrogue-v1-full
```

自动找最新的 `*_steps.zip`（没有则回退到 `final_model.zip`），累计步数继续往上加。
`--timesteps` 可覆盖配置里的总量。

## 6. 评估 checkpoint

```bash
.venv/bin/python -m rl_game_agent.evaluate \
  --model runs/ruggrogue-v1-full/checkpoints/ppo_ruggrogue_100000_steps.zip \
  --episodes 10 --out evals/ckpt-100k
```

基线对照：`--baseline random` / `--baseline wait` / `--baseline none`（默认）。
主指标 `mean_max_depth`，看终端表格和 `evals/ckpt-100k/summary.json`。

## 7. 产物位置一览

| 产物 | 路径 |
|---|---|
| 训练配置 | `configs/ruggrogue_ppo_v1.yaml` |
| 周期 checkpoint | `runs/<out>/checkpoints/ppo_ruggrogue_<steps>_steps.zip` |
| 最终模型 | `runs/<out>/final_model.zip` |
| TensorBoard | `runs/<out>/tb/` |
| 训练日志 | `runs/<out>/train.log`（nohup 重定向） |
| 评估报告 | `evals/<name>/summary.json` + `episodes.jsonl` |

## 8. 常见问题

- **浏览器起不来**：`sudo .venv/bin/playwright install-deps chromium` 装系统依赖；root 用户若报 sandbox 问题，检查 chromium 是否需要 `--no-sandbox`（本 VM root 下可直接跑）
- **`:8901` 没服务**：`python3 -m http.server 8901 --directory vendor/ruggrogue-web`（train.py 启动时也会自动拉起）
- **游戏文件校验失败**：删掉 `vendor/ruggrogue-web/` 重跑 setup 脚本；官网文件变更会导致 sha256 对不上，此时不要强行训练，先核对版本
- **CUDA 不可用**：`torch.cuda.is_available()` 为 False 时先修 torch 再训练，CPU 跑 200k 步不现实
