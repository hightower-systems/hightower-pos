from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    sentry_base_url: str = "http://sentry.local:8000"
    sentry_api_token: str = "replace-me"
    sentry_mock: bool = False
    sentry_initial_backoff_s: float = 0.5

    windcave_base_url: str = "https://sec.windcave.com/pxmi3/pos.aspx"
    windcave_user: str = "AvidMax"
    windcave_key: str = "replace-me"
    windcave_station: str = "replace-with-terminal-serial"
    windcave_vendor_id: str = "Hightower"
    windcave_pos_name: str = "AvidMaxPOS"
    windcave_device_id: str = "AvidMax-Reg1"
    windcave_pos_version: str = "1.0.0"
    windcave_currency: str = "USD"
    windcave_timezone: str = "US MST"
    windcave_mock: bool = False
    windcave_poll_interval_ms: int = 1000
    windcave_max_poll_duration_s: int = 120
    windcave_initial_backoff_s: float = 0.5

    tax_rate: float = 0.0810
    tax_inclusive: bool = False

    price_csv_max_rows: int = 5000
    refund_window_days: int = 90

    fabric_transaction_service_url: str = ""
    fabric_api_key: str = ""
    fabric_request_timeout_s: float = 30.0
    fabric_sync_interval_s: int = 14400

    store_name: str = "AvidMax"
    store_address_line_1: str = ""
    store_address_line_2: str = ""
    store_phone: str = ""

    session_secret_key: str = "replace-with-random-32-bytes-base64"
    session_ttl_hours: int = 12

    database_url: str = "sqlite:///./pos.db"

    allowed_origins: str = "http://pos-vm.local,http://localhost:5173"

    log_level: str = "INFO"
    debug: bool = False

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
