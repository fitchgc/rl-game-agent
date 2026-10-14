"""Evaluation entrypoint: run a trained model and report mean reward."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained RL agent.")
    parser.add_argument("--model", required=True, help="Path to saved model (.zip)")
    parser.add_argument("--episodes", type=int, default=10)
    args = parser.parse_args()

    # TODO: load SB3 model, run episodes on the game env, report stats.
    print(f"Evaluating {args.model} over {args.episodes} episodes (not yet implemented).")


if __name__ == "__main__":
    main()
