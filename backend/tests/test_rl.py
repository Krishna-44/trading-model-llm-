import numpy as np

from aifos.rl.env import TradingEnvCore


def test_env_runs_to_done():
    close = list(100 * np.cumprod(1 + np.random.default_rng(0).normal(0.001, 0.01, 300)))
    env = TradingEnvCore(close)
    obs = env.reset()
    assert obs.shape == (4,)
    done, steps, info = False, 0, {}
    while not done and steps < 2000:
        obs, r, done, info = env.step(steps % 3)
        steps += 1
    assert done and "equity" in info and obs.shape == (4,)


def test_long_is_rewarded_on_uptrend():
    close = list(np.linspace(100, 200, 200))  # clean uptrend
    env = TradingEnvCore(close)
    env.reset()
    total, done = 0.0, False
    while not done:
        _, r, done, _ = env.step(1)  # always long
        total += r
    assert total > 0  # holding long through an uptrend earns positive reward
