"""RL trainer. PPO training runs in an ISOLATED SUBPROCESS so that a torch crash
(segfault, OOM, MPS hiccup) can never take down the API process. The API itself
never imports torch — dependency presence is checked via importlib, and training
is delegated to ``python -m aifos.rl._worker``."""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys

from .env import TradingEnvCore

logger = logging.getLogger("aifos.rl")


def _deps_ok() -> bool:
    # find_spec does NOT import the module (so torch never loads into the API)
    return all(importlib.util.find_spec(m) for m in ("gymnasium", "stable_baselines3"))


def rl_status() -> dict:
    return {
        "deps_installed": _deps_ok(),
        "algorithm": "PPO (Stable-Baselines3), trained in an isolated subprocess",
        "reward": "position·return − cost − λ·drawdown (survival-weighted)",
        "note": ("ready to train"
                 if _deps_ok() else
                 "install backend/requirements-ml.txt (torch + stable-baselines3) to train"),
    }


def train(provider, symbol: str, steps: int = 3000, interval: str = "1d") -> dict:
    close = list(provider.history(symbol, interval)["close"].values)
    if len(close) < 100:
        return {"status": "insufficient_data", "symbol": symbol}

    if not _deps_ok():
        # honest no-op: prove the env runs with a random policy (in-process, light)
        env = TradingEnvCore(close)
        env.reset()
        import random
        done, total = False, 0.0
        while not done:
            _, r, done, _ = env.step(random.randint(0, 2))  # noqa: S311 - sim only
            total += r
        return {"status": "deps_missing", "symbol": symbol,
                "random_policy_reward": round(total, 4), **rl_status()}

    # train in a subprocess — torch is sandboxed away from the API
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "aifos.rl._worker", symbol, str(int(steps)), interval],
            capture_output=True, text=True, timeout=300,
            env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", ".")},
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "symbol": symbol, "note": "training exceeded 300s"}
    if proc.returncode != 0:
        logger.warning("rl worker failed (%s): %s", proc.returncode, proc.stderr[-300:])
        return {"status": "train_failed", "symbol": symbol,
                "detail": (proc.stderr or "").strip()[-300:] or f"exit {proc.returncode}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"status": "parse_error", "symbol": symbol, "raw": proc.stdout[-300:]}
