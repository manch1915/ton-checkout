from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    public_url: str = "http://localhost:5173"
    api_url: str = "http://localhost:8000"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    database_url: str = "postgresql+asyncpg://checkout:checkout@localhost:5432/checkout"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: SecretStr = SecretStr("dev-only-secret-key-change-me-in-production")
    session_ttl_hours: int = 24 * 7

    ton_network: Literal["testnet", "mainnet"] = "testnet"
    ton_provider: Literal["toncenter", "tonapi"] = "toncenter"
    toncenter_api_key: SecretStr | None = None
    tonapi_api_key: SecretStr | None = None
    # Master contract of the jetton accepted as "USDT". On testnet it is our own test jetton.
    usdt_jetton_master: str = ""
    usdt_decimals: int = 6

    watcher_interval_seconds: float = 6.0
    invoice_ttl_minutes: int = 30
    # Tolerance for rounding in wallets that cut the last digits of nanoTON.
    underpay_tolerance_nano: int = 1_000
    # Testnet and mainnet wallets get spammed with tiny transfers carrying ads in the comment.
    # Below this amount a transfer without a payment code is recorded but kept out of review.
    dust_threshold_nano: int = 100_000_000

    stars_per_usd: float = 50.0
    webhook_retry_speedup: float = 1.0

    rates_ttl_seconds: int = 60
    fallback_ton_usd: float = 1.35

    telegram_bot_token: SecretStr | None = None
    telegram_bot_username: str = ""
    telegram_test_env: bool = True
    # For a public demo on a production bot: give Stars back right after the order is fulfilled.
    stars_auto_refund: bool = False

    ton_proof_domain: str = "localhost:5173"
    ton_proof_ttl_seconds: int = 15 * 60

    demo_enabled: bool = True
    demo_wallet_address: str = ""
    # Where the demo shop receives our webhooks. Inside docker compose this is the api service.
    shop_webhook_url: str = "http://localhost:8010/api/shop/webhook"
    rate_limit_per_minute: int = 120

    @model_validator(mode="after")
    def _strong_secret_in_prod(self) -> "Settings":
        secret = self.secret_key.get_secret_value()
        if self.env == "prod" and (len(secret) < 32 or secret.startswith("dev-only")):
            raise ValueError("SECRET_KEY must be a random string of at least 32 characters")
        return self

    @property
    def is_testnet(self) -> bool:
        return self.ton_network == "testnet"


@lru_cache
def get_settings() -> Settings:
    return Settings()
