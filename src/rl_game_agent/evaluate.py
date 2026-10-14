"""Unified evaluation harness (impl ticket 09, wayfinder eval protocol).

Custom loop (not SB3 EvalCallback) so every info key is captured:
phase/turn/depth/hud_certain/reward_breakdown/end_reason/truncated_kind/
obs_stale/dialog_seen/sync_latency_ms.

Fault accounting (protocol):
- truncated_kind in {"fault", "ocr"} -> whole attempt EXCLUDED from policy
  metrics, counted in fault stats, reported separately.
- "budget"/"stagnation" truncations and deaths -> COUNTED (policy outcomes).
- obs_stale attempts are counted but flagged.
- fault_attempts > 2 -> LINK-RED (exit code 2), the point is not selectable.
- zero valid attempts -> metrics reported as unavailable, never zero.

Exit codes: 0 = ok, 2 = LINK-RED, 1 = error (partial results still kept).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from .envs import ENV_REGISTRY

# truncated_kind values that mark a LINK failure (whole attempt excluded).
FAULT_KINDS = {"fault", "ocr"}

# LINK-RED threshold (protocol): more than this many fault attempts in one run.
LINK_RED_FAULTS = 2

WAIT_ACTION = 8  # wait-only baseline: constant '.' (ticket 05)


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable without a browser)
# ---------------------------------------------------------------------------


def classify_attempt(rec: dict[str, Any]) -> str:
    """Return 'fault' or 'valid' for a finished attempt record."""
    if rec.get("crashed"):
        return "fault"
    if rec.get("truncated_kind") in FAULT_KINDS:
        return "fault"
    return "valid"


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate attempt records into the protocol summary."""
    valid = [r for r in records if classify_attempt(r) == "valid"]
    fault = [r for r in records if classify_attempt(r) == "fault"]

    depths = [r["max_depth"] for r in valid if r.get("max_depth") is not None]
    turns = [r["max_turn"] for r in valid if r.get("max_turn") is not None]

    def stats(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"n": 0, "mean": None, "std": None, "median": None,
                    "min": None, "max": None}
        a = np.asarray(xs, dtype=float)
        return {"n": int(a.size), "mean": float(a.mean()),
                "std": float(a.std(ddof=1)) if a.size > 1 else 0.0,
                "median": float(np.median(a)),
                "min": float(a.min()), "max": float(a.max())}

    lat = [s for r in records for s in r.get("sync_latency_ms", [])]
    stale_steps = sum(r.get("obs_stale_steps", 0) for r in records)
    uncertain_steps = sum(r.get("hud_uncertain_steps", 0) for r in records)
    total_steps = sum(r.get("n_steps", 0) for r in records)

    fault_kinds: dict[str, int] = {}
    for r in fault:
        k = r.get("truncated_kind") or ("crash" if r.get("crashed") else "unknown")
        fault_kinds[str(k)] = fault_kinds.get(str(k), 0) + 1

    return {
        "attempts": len(records),
        "valid_attempts": len(valid),
        "fault_attempts": len(fault),
        "fault_kinds": fault_kinds,
        "fault_rate": (len(fault) / len(records)) if records else None,
        "mean_max_depth": stats(depths)["mean"],
        "max_depth_stats": stats(depths),
        "survival_turns_stats": stats(turns),
        "obs_stale_rate": (stale_steps / total_steps) if total_steps else None,
        "ocr_uncertain_rate": (uncertain_steps / total_steps) if total_steps else None,
        "sync_latency_ms": {
            "p50": float(np.percentile(lat, 50)) if lat else None,
            "p95": float(np.percentile(lat, 95)) if lat else None,
            "n": len(lat),
        },
        "link_red": len(fault) > LINK_RED_FAULTS,
        "metrics_available": bool(valid),
    }


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------


class _ModelPolicy:
    """SB3 checkpoint policy (deterministic flag per protocol)."""

    def __init__(self, model_path: str, deterministic: bool = True) -> None:
        from stable_baselines3 import PPO  # lazy: baselines only need numpy

        # PPO is the v1 algorithm (ticket 08); try the generic loader first so
        # other SB3 algos keep working if the ticket-08 decision ever changes.
        try:
            from stable_baselines3 import load as _load  # type: ignore
        except Exception:  # pragma: no cover - very old SB3
            _load = None  # type: ignore
        if _load is not None:
            self.model = _load(model_path)
        else:
            self.model = PPO.load(model_path)
        self.deterministic = deterministic
        self.name = f"model:{Path(model_path).name}"

    def __call__(self, obs: np.ndarray) -> int:
        mo = obs
        want = self.model.observation_space.shape
        # Training wraps (84,84) uint8 -> channel-first (ticket 08); mirror it.
        if want is not None and len(want) == 3 and mo.ndim == 2:
            mo = mo[np.newaxis, ...]
        action, _ = self.model.predict(mo, deterministic=self.deterministic)
        return int(np.asarray(action).item())


class _RandomPolicy:
    def __init__(self, action_space, seed: int = 0) -> None:
        self.action_space = action_space
        self.rng = np.random.default_rng(seed)
        self.name = f"random(seed={seed})"

    def __call__(self, obs: np.ndarray) -> int:
        return int(self.rng.integers(0, self.action_space.n))


class _WaitPolicy:
    def __init__(self) -> None:
        self.name = "wait-only"

    def __call__(self, obs: np.ndarray) -> int:
        return WAIT_ACTION


# ---------------------------------------------------------------------------
# Attempt runner
# ---------------------------------------------------------------------------


def run_attempt(env, policy, attempt_idx: int, deadline: float) -> dict[str, Any]:
    """Run one attempt; never raises for game faults (they become records)."""
    rec: dict[str, Any] = {
        "attempt": attempt_idx,
        "policy": policy.name,
        "n_steps": 0,
        "max_depth": None,
        "max_turn": None,
        "end_reason": None,
        "truncated_kind": None,
        "total_reward": 0.0,
        "crashed": False,
        "crash_info": None,
        "sync_latency_ms": [],
        "obs_stale_steps": 0,
        "hud_uncertain_steps": 0,
        "wall_s": 0.0,
    }
    t0 = time.time()
    try:
        obs, info = env.reset()
        done = False
        while not done:
            if time.time() > deadline:
                rec["end_reason"] = "eval_wallclock_exceeded"
                rec["truncated_kind"] = "eval_budget"
                break
            action = policy(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            rec["n_steps"] += 1
            rec["total_reward"] += float(reward)
            d, t = info.get("depth"), info.get("turn")
            if d is not None:
                rec["max_depth"] = d if rec["max_depth"] is None else max(rec["max_depth"], d)
            if t is not None:
                rec["max_turn"] = t if rec["max_turn"] is None else max(rec["max_turn"], t)
            if info.get("obs_stale"):
                rec["obs_stale_steps"] += 1
            if not info.get("hud_certain", True):
                rec["hud_uncertain_steps"] += 1
            lat = info.get("sync_latency_ms")
            if lat:
                rec["sync_latency_ms"].append(float(lat))
            if terminated or truncated:
                done = True
                rec["end_reason"] = info.get("end_reason")
                rec["truncated_kind"] = info.get("truncated_kind")
    except Exception as e:  # noqa: BLE001 - faults become records, never crash eval
        rec["crashed"] = True
        rec["crash_info"] = f"{type(e).__name__}: {e}"
        rec["end_reason"] = "eval_crash"
    rec["wall_s"] = round(time.time() - t0, 1)
    rec["verdict"] = classify_attempt(rec)
    return rec


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Unified evaluation harness (ticket 09).")
    p.add_argument("--model", default=None,
                   help="Path to SB3 model .zip (required unless --baseline is set)")
    p.add_argument("--episodes", type=int, default=10, help="Fixed attempts per run")
    p.add_argument("--deterministic", dest="deterministic", action="store_true",
                   default=True, help="Deterministic model predictions (default on)")
    p.add_argument("--no-deterministic", dest="deterministic", action="store_false")
    p.add_argument("--baseline", choices=["none", "random", "wait"], default="none")
    p.add_argument("--out", default=None, help="Output dir (default artifacts/eval/<run_id>)")
    p.add_argument("--max-eval-minutes", type=float, default=30.0)
    p.add_argument("--seed", type=int, default=0, help="RNG seed for baselines only")
    return p


def _print_table(summary: dict[str, Any], records: list[dict[str, Any]]) -> None:
    md = summary["max_depth_stats"]
    st = summary["survival_turns_stats"]
    lat = summary["sync_latency_ms"]
    print("\n==== evaluation summary ====")
    print(f"attempts: {summary['attempts']}  valid: {summary['valid_attempts']}  "
          f"fault: {summary['fault_attempts']}  fault_kinds: {summary['fault_kinds'] or '-'}")
    if summary["metrics_available"]:
        print(f"mean_max_depth: {md['mean']:.2f}  (std {md['std']:.2f}, "
              f"median {md['median']:.0f}, range {md['min']:.0f}-{md['max']:.0f})")
        print(f"mean_survival_turns: {st['mean']:.1f}")
    else:
        print("mean_max_depth: UNAVAILABLE (zero valid attempts)")
    print(f"fault_rate: {summary['fault_rate']:.2%}  "
          f"obs_stale_rate: {(summary['obs_stale_rate'] or 0):.2%}  "
          f"ocr_uncertain_rate: {(summary['ocr_uncertain_rate'] or 0):.2%}")
    print(f"sync_latency_ms p50/p95: {lat['p50']}/{lat['p95']}  "
          f"LINK-RED: {summary['link_red']}")
    print("attempt | verdict | steps | max_depth | max_turn | end_reason")
    for r in records:
        print(f"{r['attempt']:7d} | {r['verdict']:7s} | {r['n_steps']:5d} | "
              f"{str(r['max_depth']):9s} | {str(r['max_turn']):8s} | {r['end_reason']}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.baseline == "none" and not args.model:
        print("error: --model is required unless --baseline is set", file=sys.stderr)
        return 1
    if args.episodes < 1:
        print("error: --episodes must be >= 1", file=sys.stderr)
        return 1

    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{args.baseline}"
    out = Path(args.out) if args.out else Path("artifacts") / "eval" / run_id
    out.mkdir(parents=True, exist_ok=True)

    # Fresh eval env from the factory: independent browser, never the training env.
    env = ENV_REGISTRY["ruggrogue-v1"]()
    if args.baseline == "random":
        policy: Any = _RandomPolicy(env.action_space, seed=args.seed)
    elif args.baseline == "wait":
        policy = _WaitPolicy()
    else:
        policy = _ModelPolicy(args.model, deterministic=args.deterministic)

    deadline = time.time() + args.max_eval_minutes * 60
    records: list[dict[str, Any]] = []
    exit_code = 0
    try:
        for i in range(args.episodes):
            if time.time() > deadline:
                print(f"wall-clock budget exceeded after {i} attempts; "
                      f"keeping partial results")
                break
            rec = run_attempt(env, policy, i, deadline)
            records.append(rec)
            with (out / "episodes.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
    except KeyboardInterrupt:
        print("interrupted; keeping partial results", file=sys.stderr)
        exit_code = 1
    finally:
        try:
            env.close()
        except Exception:
            pass

    summary = summarize(records)
    summary.update({
        "run_id": run_id,
        "policy": policy.name,
        "episodes_requested": args.episodes,
        "deterministic": args.deterministic if args.baseline == "none" else None,
        "seed": args.seed,
        "max_eval_minutes": args.max_eval_minutes,
        "note": "game not seedable (game_seedable=False); --seed controls baseline RNG only",
    })
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _print_table(summary, records)
    print(f"\nartifacts: {out}/episodes.jsonl {out}/summary.json")

    if summary["link_red"]:
        print("LINK-RED: fault_attempts > 2; this point is not selectable", file=sys.stderr)
        return 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
