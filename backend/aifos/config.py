"""Central configuration. All settings are env-overridable with the ``AIFOS_`` prefix.

The live-trading gate lives here and defaults to OFF. Nothing in the system can
route a real order unless ``live_trading_enabled`` is explicitly True *and* the
selected broker has credentials configured.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIFOS_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- App ---
    app_name: str = "AIFOS"
    env: str = "local"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # --- Persistence (SQLite local-first; swap to Postgres/Timescale via URL) ---
    database_url: str = "sqlite:///./aifos.db"
    data_cache_dir: str = "./.cache"

    # --- Market universe (real data via yfinance, no keys needed) ---
    # Indian equities + indices + FX + crypto — satisfies "indian + forex all".
    universe: list[str] = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS",  # NSE equities
        "^NSEI", "^NSEBANK",                                # Nifty 50, Bank Nifty
        "USDINR=X", "EURINR=X", "EURUSD=X", "GBPUSD=X",     # forex
        "BTC-USD", "ETH-USD",                               # crypto (24/7)
    ]
    default_symbol: str = "^NSEI"
    default_interval: str = "1d"

    # --- Capital / paper account ---
    starting_capital: float = 1_000_000.0  # ₹10L paper book
    base_currency: str = "INR"

    # --- Risk gates (the system's spine) ---
    confidence_threshold: float = 0.62      # below this -> HOLD, no exceptions
    max_position_pct: float = 0.10          # max 10% of equity in one position
    max_open_positions: int = 5
    max_daily_loss_pct: float = 0.03        # 3% daily loss -> kill switch trips
    max_portfolio_exposure_pct: float = 0.60
    risk_per_trade_pct: float = 0.0075      # risk 0.75% of equity per trade
    atr_stop_mult: float = 2.0              # stop = entry - 2*ATR (long)
    atr_target_mult: float = 3.0            # target = entry + 3*ATR -> R:R 1.5
    per_trade_cap: float = 100_000.0        # hard absolute cap per order (base ccy)
    min_rr_ratio: float = 1.5               # reject trades below this reward:risk

    # News alignment gate (loss-avoidance: never trade INTO opposing/uncertain news)
    news_veto_impact: float = 0.4           # block trades against news at/above this impact
    news_event_impact: float = 0.6          # impact level that counts as a "major event"
    news_event_confidence: float = 0.70     # confidence required to trade through a major event

    # --- Live trading gate (DANGER ZONE — defaults OFF) ---
    live_trading_enabled: bool = False
    broker: str = "paper"  # paper | zerodha | upstox | angelone | oanda
    allow_offshore_forex: bool = False  # FEMA guard for Indian residents

    # Broker credentials (only read when live + matching broker selected)
    zerodha_api_key: str = ""
    zerodha_api_secret: str = ""
    zerodha_access_token: str = ""
    oanda_api_token: str = ""
    oanda_account_id: str = ""
    oanda_environment: str = "practice"  # practice | live

    # Angel One SmartAPI (NSE equity + currency F&O). TOTP secret required.
    angelone_api_key: str = ""
    angelone_client_code: str = ""
    angelone_pin: str = ""
    angelone_totp_secret: str = ""

    # --- Alerts (Telegram / Discord webhooks; optional) ---
    alerts_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""

    # --- News sources (Yahoo per-symbol is keyless; RSS broadens market news) ---
    news_api_key: str = ""  # optional NewsAPI key for per-symbol keyword search
    rss_feeds: list[str] = [
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "https://www.moneycontrol.com/rss/business.xml",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    ]

    # --- LLM agent layer (augments deterministic quant; optional) ---
    llm_provider: str = "ollama"  # ollama | anthropic | openai | none
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_timeout_s: float = 20.0

    # --- Assistant ("Vision") — voice/chat desk assistant grounded in AIFOS data ---
    assistant_name: str = "Vision"
    groq_api_key: str = ""  # reuse your Groq key; falls back to data-driven answers if unset
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: str = ""  # Google Gemini (used if Groq absent)
    gemini_model: str = "gemini-2.5-flash"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
