"""Tests for risk.vol_gate — verify hard volatility regime blocks."""
from __future__ import annotations

import os

import pytest

from aifos.risk.vol_gate import check


def test_panic_regime_blocks():
    r = check({"regime": "panic", "vol_ratio": 2.8})
    assert r.blocked is True
    assert "panic" in r.reason.lower()


def test_volatile_high_vol_ratio_blocks():
    r = check({"regime": "volatile", "vol_ratio": 1.95})
    assert r.blocked is True
    assert "volatile" in r.reason.lower()


def test_volatile_low_vol_ratio_allows():
    # Volatile but vol_ratio below the hard threshold — soft trim handles it.
    r = check({"regime": "volatile", "vol_ratio": 1.6})
    assert r.blocked is False


def test_trending_allows():
    r = check({"regime": "trending_up", "vol_ratio": 1.2})
    assert r.blocked is False


def test_ranging_allows():
    r = check({"regime": "ranging", "vol_ratio": 0.9})
    assert r.blocked is False


def test_vix_threshold_blocks():
    # Even in a benign regime, sky-high India VIX blocks.
    r = check({"regime": "ranging", "vol_ratio": 0.9}, india_vix=25.0)
    assert r.blocked is True
    assert "vix" in r.reason.lower()


def test_vix_low_allows():
    r = check({"regime": "ranging", "vol_ratio": 0.9}, india_vix=14.0)
    assert r.blocked is False


def test_env_override(monkeypatch):
    monkeypatch.setenv("AIFOS_VOL_GATE_VIX_THRESHOLD", "30")
    r = check({"regime": "ranging", "vol_ratio": 0.9}, india_vix=25.0)
    # Raised threshold from 22 to 30 → 25 no longer blocks.
    assert r.blocked is False


def test_unknown_regime_allows():
    r = check({"regime": "unknown", "vol_ratio": 1.0})
    assert r.blocked is False


def test_none_regime_safe():
    r = check(None)  # type: ignore[arg-type]
    assert r.blocked is False
