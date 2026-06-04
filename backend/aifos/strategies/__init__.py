from .base import Strategy, StrategySignal
from .mean_reversion import MeanReversionStrategy
from .momentum import MomentumStrategy

REGISTRY: dict[str, type[Strategy]] = {
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
}


def build_strategy(name: str, **params) -> Strategy:
    if name not in REGISTRY:
        raise KeyError(f"unknown strategy '{name}'; have {list(REGISTRY)}")
    return REGISTRY[name](**params)


__all__ = [
    "Strategy", "StrategySignal", "MomentumStrategy", "MeanReversionStrategy",
    "REGISTRY", "build_strategy",
]
