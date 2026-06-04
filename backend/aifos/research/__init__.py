"""OpenBB-style research layer (additive, optional).

Standardized financial-research data behind a provider abstraction — mirroring
OpenBB's design. Works today via free sources (yfinance); if the `openbb` SDK is
installed it is used for richer/standardized metrics. The core platform does not
depend on this module, so installing it changes nothing about how AIFOS runs.
"""
from .fundamentals import Fundamentals, FundamentalsClient, get_fundamentals_client

__all__ = ["Fundamentals", "FundamentalsClient", "get_fundamentals_client"]
