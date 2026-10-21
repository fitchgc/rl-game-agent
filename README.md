# rl-game-agent

Train reinforcement-learning agents with stable-baselines3 to play games automatically.

[中文 README](README.zh.md)

## Overview / How it works

The first target is **ruggrogue v1.0.1**, a turn-based web roguelike
that runs in the browser as WebAssembly.

The agent interacts with the game through a real browser rather than a
game-specific simulation:

1. A local static server serves the game on port **8901**.
2. Playwright drives a headless Chromium instance.
3. Canvas screenshots become single-frame **84 × 84 grayscale** observations.
4. Fixed-font template matching reads the game's HUD.
5. Environment steps are synchronized with the HUD **Turn** counter.

The HUD reader extracts **Turn, Depth, Health, Experience, and Level**.
Tesseract was evaluated but rejected because it systematically misread
the game's pixel font.

### Actions

The action space is **`Discrete(10)`**:

- Eight vi movement keys.
- Wait.
- A descend-stairs macro that includes a dialog handshake.

### Rewards

The reward contract combines:

- Progress rewards for reaching a new maximum depth, leveling up, and gaining XP.
- A small per-step penalty.
- A death penalty.
- A win bonus.

Progress rewards apply only to new records, preventing repeated progress
from being farmed for reward.

## Architecture

The environment separates browser interaction from game-specific behavior:

| Component | Role |
| --- | --- |
| `BrowserGameEnv` | Generic browser-game Gymnasium environment. |
| `GameAdapter` | Per-game adaptation layer. |
| ruggrogue adapter | Game-specific integration for ruggrogue. |
| Environment registry | Registers ruggrogue as `ruggrogue-v1`. |

Training uses **PPO** with **`CnnPolicy` (NatureCNN)**.
The unified evaluation entry point is `evaluate.py`.

Evaluation reports **`mean_max_depth`** as its primary metric.
Fault episodes are excluded from the metric and counted separately.
Random and wait-only policies provide evaluation baselines.

## Quick start

### 1. Set up the training machine

Run the setup script:

```bash
bash scripts/setup_training_env.sh
```

The script:

- Creates `.venv`.
- Installs CUDA-enabled PyTorch and the project dependencies.
- Installs Playwright Chromium.
- Downloads the game files from the official site.
- Verifies SHA-256 checksums against `scripts/ruggrogue-manifest.json`.
- Starts the local static server on port **8901**.

See [the GPU training guide](docs/gpu-training.md) for the full setup
and training instructions.

### 2. Train

```bash
.venv/bin/python -m rl_game_agent.train --config configs/ruggrogue_ppo_v1.yaml --out runs/ruggrogue-v1-full
```

The supplied configuration targets **200,000 total timesteps**,
saves checkpoints every **10,000 steps**, and enables TensorBoard logging.

### 3. Resume training

Add `--resume` with the existing run directory:

```bash
.venv/bin/python -m rl_game_agent.train --config configs/ruggrogue_ppo_v1.yaml --out runs/ruggrogue-v1-full --resume runs/ruggrogue-v1-full
```

### 4. Evaluate a checkpoint

For example, evaluate the 100,000-step checkpoint over 10 episodes:

```bash
.venv/bin/python -m rl_game_agent.evaluate --model runs/ruggrogue-v1-full/checkpoints/ppo_ruggrogue_100000_steps.zip --episodes 10 --out evals/ckpt-100k
```

This command requires the referenced checkpoint to exist.

## Configuration notes

The training configuration is `configs/ruggrogue_ppo_v1.yaml`.

- **Algorithm:** PPO with `CnnPolicy` and NatureCNN.
- **Training budget:** 200,000 total timesteps.
- **Checkpoint interval:** 10,000 steps.
- **Logging:** TensorBoard.
- **Parallel environments:** Optional, configured through `num_envs`.

Each parallel environment runs its own headless Chromium instance.

Training includes safety abort rules for the fault-episode rate,
non-finite rewards or losses, and a **72-hour wall-clock cap**.

## Project status

The full pipeline is **implemented and verified**:

- Browser environment and reward logic.
- Training smoke test.
- Evaluation.
- Checkpoint saving and resume.

Long training runs use a local GPU machine. Environment stepping is
browser-bound at approximately **one step per second per environment**.
The GPU mainly accelerates PPO updates; parallel environments are the
main lever for improving throughput.

## Repository layout

```text
src/rl_game_agent/
├── train.py
├── evaluate.py
└── envs/
    ├── browser_env.py
    ├── ruggrogue.py
    └── hud_ocr.py
configs/
scripts/
docs/
├── gpu-training.md
└── (agent workflow docs)
vendor/                         # Game files; fetched at setup, not in Git
runs/                           # Checkpoints and logs; not in Git
```

## License / Credits

**ruggrogue** is licensed under **MIT for its code** and **CC0 for its tiles**.

This project vendors only the game's web build, fetched from the official
site during setup. The game files are not stored in Git.

The agent pipeline uses stable-baselines3, Gymnasium, Playwright, and Chromium.
