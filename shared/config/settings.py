from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── AI / LLM ──────────────────────────────────────────────────────────────
    anthropic_api_key: SecretStr = Field(..., description="Anthropic Claude API key")
    claude_model: str = Field("claude-sonnet-4-20250514", description="Claude model ID")

    # ── Exchange: MEXC ────────────────────────────────────────────────────────
    mexc_api_key: SecretStr = Field(...)
    mexc_secret: SecretStr = Field(...)

    # ── Exchange: Bitget ──────────────────────────────────────────────────────
    bitget_api_key: SecretStr = Field(...)
    bitget_secret: SecretStr = Field(...)
    bitget_passphrase: SecretStr = Field(...)

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_bot_token: SecretStr = Field(...)
    telegram_chat_id: str = Field(...)

    # ── On-Chain APIs ─────────────────────────────────────────────────────────
    glassnode_api_key: SecretStr = Field(default="")   # deprecated — no usado
    etherscan_api_key: SecretStr = Field(default="")   # Etherscan free tier
    cryptoquant_api_key: SecretStr = Field(default="") # CryptoQuant free tier
    solscan_api_key: SecretStr = Field(default="")

    # ── Market Data ───────────────────────────────────────────────────────────
    coingecko_api_key: SecretStr = Field(default="")
    coinmarketcap_api_key: SecretStr = Field(default="")

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field("postgresql+asyncpg://postgres:password@localhost:5432/crypto_agent")
    postgres_user: str = Field("postgres")
    postgres_password: SecretStr = Field("password")
    postgres_db: str = Field("crypto_agent")

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field("redis://localhost:6379/0")

    # ── JWT Auth ──────────────────────────────────────────────────────────────
    jwt_secret_key: SecretStr = Field(...)
    jwt_algorithm: str = Field("HS256")
    jwt_access_token_expire_minutes: int = Field(60)
    dashboard_username: str = Field("admin")
    dashboard_password: SecretStr = Field(...)

    # ── Scheduler ─────────────────────────────────────────────────────────────
    discovery_schedule_hour: int = Field(2, ge=0, le=23)
    monitor_interval_seconds: int = Field(300, ge=60)
    learner_schedule_hour: int = Field(3, ge=0, le=23)

    # ── Capital y Distribución ────────────────────────────────────────────────
    capital_total_usd: float = Field(1000.0, gt=0)
    mexc_allocation_pct: float = Field(69.0, ge=0, le=100)
    bitget_allocation_pct: float = Field(31.0, ge=0, le=100)

    # ── Umbrales de Detección ─────────────────────────────────────────────────
    alert_threshold: float = Field(70.0, ge=0, le=100)
    llm_validation_threshold: float = Field(85.0, ge=0, le=100)
    inflow_threshold_usd: float = Field(500_000.0, gt=0)
    holder_concentration_threshold: float = Field(60.0, ge=0, le=100)
    short_interest_threshold: float = Field(20.0, ge=0, le=100)

    # ── Gestión de Riesgo ─────────────────────────────────────────────────────
    stop_loss_pct: float = Field(8.0, gt=0)
    take_profit_1_pct: float = Field(30.0, gt=0)
    take_profit_2_pct: float = Field(60.0, gt=0)
    take_profit_3_pct: float = Field(100.0, gt=0)
    max_daily_loss_pct: float = Field(15.0, gt=0)
    max_consecutive_losses: int = Field(3, ge=1)
    circuit_breaker_hours: int = Field(24, ge=1)
    max_hold_hours: int = Field(72, ge=1)

    # ── Modo de Operación ─────────────────────────────────────────────────────
    paper_trading: bool = Field(True)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field("INFO")

    # ── Observabilidad ────────────────────────────────────────────────────────
    sentry_dsn: str = Field(default="")
    prometheus_port: int = Field(8000)

    @property
    def mexc_capital_usd(self) -> float:
        return self.capital_total_usd * (self.mexc_allocation_pct / 100)

    @property
    def bitget_capital_usd(self) -> float:
        return self.capital_total_usd * (self.bitget_allocation_pct / 100)


# Singleton accesible desde cualquier módulo
settings = Settings()
