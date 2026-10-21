# rl-game-agent

用 [stable-baselines3](https://github.com/DLR-RM/stable-baselines3) 训练强化学习智能体，让模型自动玩游戏。

## 目标

- 选择一个目标游戏并封装成 Gymnasium 环境
- 用 PPO（或其它 SB3 算法）训练自动游玩策略
- 评估、保存并可复现最佳模型

> 目标游戏、环境封装方式与训练路线图待定 —— 由 `wayfinder` 规划为决策 ticket 逐一解决。

## 快速开始

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 训练（默认 PPO 配置）
python -m rl_game_agent.train --config configs/ppo_default.yaml

# 评估
python -m rl_game_agent.evaluate --model models/best_model.zip
```

## 目录结构

```
src/rl_game_agent/
  envs/        # 游戏环境封装（Gymnasium Env）
  train.py     # 训练入口
  evaluate.py  # 评估入口
configs/       # 训练超参数配置
docs/          # ADR 与领域文档
```

## 当前状态

项目骨架已就绪；训练目标与里程碑见 issue tracker（`docs/agents/issue-tracker.md`）。
