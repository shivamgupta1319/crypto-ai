"""Central configuration for the crypto-ai paper-trading system.

All risk/capital knobs live here so they apply identically to backtesting,
the live scanner, paper trading, and (later) live broker trading.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CRYPTOAI_", env_file=".env", extra="ignore")

    # --- App ---
    app_name: str = "crypto-ai"
    debug: bool = True

    # --- Market / universe ---
    symbols: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    timeframes: list[str] = ["5m", "15m", "1h", "4h", "1d"]
    # Binance USDⓈ-M futures public REST base (no API key needed for market data).
    binance_futures_base: str = "https://fapi.binance.com"
    fng_url: str = "https://api.alternative.me/fng/?limit=30"

    # --- Paper account / capital ---
    initial_capital: float = 100_000.0  # base units (USDT-equivalent); ₹1,00,000
    display_currency: str = "USDT"      # UI label only; math is in this unit

    # --- Risk management (enforced in PaperBroker; apply to live later too) ---
    risk_per_trade_pct: float = 1.0     # % of equity risked per trade
    max_leverage: float = 30.0          # hard cap (1–30x available in the UI)
    default_leverage: float = 5.0
    max_concurrent_positions: int = 5
    max_position_pct: float = 30.0      # max notional as % of equity (pre-leverage)
    daily_max_loss_pct: float = 5.0     # kill switch: stop new trades for the day
    # Exchange maintenance-margin rate (% of notional); used only to estimate the
    # liquidation price more realistically than the naive initial-margin formula.
    maintenance_margin_pct: float = 0.5
    # Trailing stop: once price moves trail_activate_pct in favor, ratchet the stop
    # to trail_distance_pct behind the current price (never loosens).
    trailing_enabled: bool = True
    trail_activate_pct: float = 1.0
    trail_distance_pct: float = 1.0

    # Correlation guard: when a new entry is highly correlated *and* same-direction
    # with the open book, scale its size down (concentration control). Reuses the
    # market correlation matrix; applied once per scan cycle.
    correlation_guard_enabled: bool = True
    correlation_threshold: float = 0.8   # Pearson corr of returns above which to scale down
    correlation_scale: float = 0.5       # size multiplier applied when the guard trips

    # --- Live scanner ---
    scan_interval_seconds: int = 60

    # --- Alerts (user-provided; keep in .env, gitignored; all free, no card) ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""

    # --- Live price stream (Binance markPrice WS; falls back to REST) ---
    price_stream_enabled: bool = True

    # --- Adaptive layer / meta-labeling (N10) ---
    # When enabled, the meta-label model gates new paper entries by P(win). Off by
    # default — it's an agent lever the user opts into (propose-and-approve).
    meta_label_enabled: bool = False
    meta_label_threshold: float = 0.55  # take a signal only if P(win) >= this

    # --- AI layer (advisory only; never sizes or places trades) ---
    # Keys go in .env (gitignored); both providers have free tiers, no card.
    ai_provider: str = "auto"  # auto | gemini | openrouter | none
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    # Extra free OpenRouter models tried in order after openrouter_model — so a
    # rate-limited/congested free model rolls over to the next one. Override via
    # CRYPTOAI_OPENROUTER_FALLBACK_MODELS (JSON list) in .env if desired.
    openrouter_fallback_models: list[str] = [
        "openai/gpt-oss-120b:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "google/gemma-4-31b-it:free",
    ]
    # Beyond the curated list above, also auto-discover currently-live free models
    # from OpenRouter so the chain self-heals as model IDs change. Total attempts
    # are capped so a fully rate-limited run doesn't stall.
    openrouter_autodiscover: bool = True
    openrouter_max_models: int = 8
    ai_request_timeout: float = 30.0
    ai_max_output_tokens: int = 700

    @property
    def active_ai_provider(self) -> str | None:
        """The provider that will actually be used given configured keys, or None."""
        p = (self.ai_provider or "auto").lower()
        if p == "none":
            return None
        if p == "gemini":
            return "gemini" if self.gemini_api_key else None
        if p == "openrouter":
            return "openrouter" if self.openrouter_api_key else None
        # auto: prefer Gemini, fall back to OpenRouter.
        if self.gemini_api_key:
            return "gemini"
        if self.openrouter_api_key:
            return "openrouter"
        return None

    @property
    def ai_enabled(self) -> bool:
        return self.active_ai_provider is not None

    @property
    def alerts_enabled(self) -> bool:
        return bool((self.telegram_bot_token and self.telegram_chat_id) or self.discord_webhook_url)
    # Fees/funding approximation for realistic paper P&L.
    taker_fee_pct: float = 0.04         # Binance futures taker fee per side
    funding_rate_pct_per_8h: float = 0.01

    # --- Storage ---
    db_path: Path = BASE_DIR / "cryptoai.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
