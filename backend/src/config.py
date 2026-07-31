"""
Application settings loaded from environment variables / .env file.
All values have sensible defaults so the app runs with zero configuration.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Data provider: "yfinance" (default, free) or "fmp" (requires API key)
    data_provider: str = "yfinance"

    # Financial Modeling Prep API key — leave blank to use yfinance only
    fmp_api_key: str = ""

    # SQLite database file path (relative to backend working directory)
    database_url: str = "sqlite+aiosqlite:///./data/market_attribution.db"

    # Scheduler: time to run the daily update (24h HH:MM, US/Eastern)
    schedule_time: str = "16:15"

    # Retry schedule after primary update fails (comma-separated HH:MM)
    schedule_retries: str = "16:30,17:00"

    # Log level
    log_level: str = "INFO"

    # CORS — origins allowed to call the API (space-separated)
    # Defaults allow the Next.js dev server and production container
    cors_origins: str = "http://localhost:3000 http://frontend:3000"

    # How many days of historical prices to backfill on first startup
    backfill_days: int = 30

    # Staleness threshold: warn if holdings are older than this many business days
    holdings_stale_days: int = 5

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split() if o.strip()]


# Singleton — import this everywhere instead of instantiating Settings() yourself
settings = Settings()
