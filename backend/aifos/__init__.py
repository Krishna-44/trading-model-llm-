"""AIFOS — Artificial Intelligence Financial Operating System.

A local-first, probability-gated autonomous trading research platform.

Design philosophy (enforced in code, not just docs):
  * The honest default is to DO NOTHING. A trade is the exception, not the rule.
  * Capital preservation > profit. Every order passes risk + compliance gates.
  * Real money execution is OFF by default behind ``Settings.live_trading_enabled``.
  * The system never claims guaranteed profit; it reasons in probabilities.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
