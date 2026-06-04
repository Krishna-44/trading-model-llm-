"""Isolated PPO training worker. Run as: python -m aifos.rl._worker SYMBOL STEPS INTERVAL
Prints a single JSON line with the trained-policy evaluation. Kept separate so a
torch crash here cannot affect the API process."""
from __future__ import annotations

import json
import sys


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "^NSEI"
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
    interval = sys.argv[3] if len(sys.argv) > 3 else "1d"

    from aifos.data.providers import get_provider
    from aifos.rl.env import make_env

    close = list(get_provider().history(symbol, interval)["close"].values)

    from stable_baselines3 import PPO

    model = PPO("MlpPolicy", make_env(close), verbose=0)
    model.learn(total_timesteps=steps)

    env = make_env(close)
    obs, _ = env.reset()
    done, total, info = False, 0.0, {}
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, r, done, _, info = env.step(action)
        total += r

    from aifos.rl.env import buy_hold_equity
    print(json.dumps({
        "status": "trained", "symbol": symbol, "timesteps": steps,
        "eval_reward": round(float(total), 4),
        "final_equity": round(float(info.get("equity", 1.0)), 4),
        "buy_hold_equity": buy_hold_equity(close),
    }))


if __name__ == "__main__":
    main()
