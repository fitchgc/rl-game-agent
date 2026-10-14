"""Training entrypoint: train an SB3 agent on a registered game environment."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml


def load_config(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train an RL agent to play a game.")
    parser.add_argument("--config", default="configs/ppo_default.yaml")
    parser.add_argument("--timesteps", type=int, default=None)
    parser.add_argument("--out", default="models")
    args = parser.parse_args()

    config = load_config(args.config)
    print(f"Loaded config: {args.config}")
    print(f"Algorithm: {config['algo']}, env: {config['env']}")

    # TODO: resolve env from envs.ENV_REGISTRY, build SB3 model, train, save.
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print("Training not yet wired to a game environment (see wayfinder tickets).")


if __name__ == "__main__":
    main()
