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
    windcave_user: str = "Hightower"
    windcave_key: str = "replace-me"
    windcave_station: str = "replace-with-terminal-serial"
    windcave_vendor_id: str = "Hightower"
    windcave_pos_name: str = "HightowerPOS"
    windcave_device_id: str = "Hightower-Reg1"
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
    fabric_outbox_drain_interval_s: int = 5
    fabric_outbox_batch_size: int = 50
    fabric_price_catalog_path: str = "/api/v1/prices/catalog"
    fabric_sales_orders_path: str = "/api/v1/sales_orders"
    fabric_customer_lookup_path: str = "/api/v1/customers/lookup"
    fabric_customer_create_path: str = "/api/v1/customers"
    fabric_auth_header_name: str = "Authorization"
    fabric_auth_header_value_prefix: str = "Bearer "

    store_name: str = "Hightower"
    store_address_line_1: str = ""
    store_address_line_2: str = ""
    store_phone: str = ""

    # Root directory for generated till-close PDFs. Production deploys
    # mount this at /data/till_pdfs so the files survive container
    # restarts on the same Docker volume that holds pos.db. Dev/test
    # overrides to a workspace-local dir via .env.
    till_pdf_root: str = "/data/till_pdfs"

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
