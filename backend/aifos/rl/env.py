"""Reinforcement-learning trading environment.

State = [rsi, realized-vol, last-return, position]; actions = {flat, long, short}.
Reward (per step) = scale · ( pnl − λ·Δdrawdown ), where pnl = position·next_return
− turnover·cost and Δdrawdown only penalizes NEW drawdown beyond the prior peak.
This rewards capturing trends while punishing fresh losses — survival-weighted,
not raw P&L — and the reward is scaled so PPO gets usable gradients. The risk
engine still gates any policy in production.

``TradingEnvCore`` is pure-numpy and testable with no heavy deps. ``make_env``
wraps it as a Gymnasium env for Stable-Baselines3 when those are installed."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import realized_vol, rsi


class TradingEnvCore:
    def __init__(self, close: list[float], cost_bps: float = 5.0,
                 dd_penalty: float = 0.3, reward_scale: float = 100.0) -> None:
        s = pd.Series(close, dtype=float)
        self.close = s.values
        self.rsi = (rsi(s) / 100).fillna(0.5).values
        self.vol = realized_vol(s, 20).fillna(0.0).clip(0, 2).values
        self.ret = s.pct_change().fillna(0.0).values
        self.cost = cost_bps / 1e4
        self.dd_penalty = dd_penalty
        self.reward_scale = reward_scale
        self.n = len(self.close)
        self.reset()

    def reset(self):
        self.t = 20
        self.position = 0.0
        self.equity = 1.0
        self.peak = 1.0
        self.prev_dd = 0.0
        return self._obs()

    def _obs(self) -> np.ndarray:
        return np.array([self.rsi[self.t], self.vol[self.t], self.ret[self.t], self.position],
                        dtype=np.float32)

    def step(self, action: int):
        target = {0: 0.0, 1: 1.0, 2: -1.0}.get(int(action), 0.0)
        turn = abs(target - self.position)
        self.position = target
        nxt = self.ret[self.t + 1] if self.t + 1 < self.n else 0.0
        pnl = self.position * nxt - turn * self.cost
        self.equity *= (1 + pnl)
        self.peak = max(self.peak, self.equity)
        drawdown = 1 - self.equity / self.peak
        dd_inc = max(0.0, drawdown - self.prev_dd)   # penalize only NEW drawdown
        self.prev_dd = drawdown
        reward = float((pnl - self.dd_penalty * dd_inc) * self.reward_scale)
        self.t += 1
        done = self.t >= self.n - 1
        return self._obs(), reward, done, {"equity": self.equity, "drawdown": drawdown}


def make_env(close: list[float]):
    """Gymnasium-wrapped env for SB3. Raises if gymnasium isn't installed."""
    import gymnasium as gym
    from gymnasium import spaces

    class TradingEnv(gym.Env):
        metadata = {"render_modes": []}

        def __init__(self):
            super().__init__()
            self.core = TradingEnvCore(close)
            self.observation_space = spaces.Box(low=-5, high=5, shape=(4,), dtype=np.float32)
            self.action_space = spaces.Discrete(3)

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            return self.core.reset(), {}

        def step(self, action):
            obs, reward, done, info = self.core.step(action)
            return obs, reward, done, False, info

    return TradingEnv()


def buy_hold_equity(close: list[float]) -> float:
    """Always-long baseline final equity over the same series (for honest comparison)."""
    env = TradingEnvCore(close)
    env.reset()
    done, info = False, {}
    while not done:
        _, _, done, info = env.step(1)
    return round(float(info.get("equity", 1.0)), 4)
