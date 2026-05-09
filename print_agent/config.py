from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    listen_host: str = "127.0.0.1"
    listen_port: int = 9100

    allowed_origin: str = "http://pos-vm.local:8080"

    printer_vendor_id: int = 0x0519
    printer_product_id: int = 0x0001
    printer_profile: str = "TSP100"
    printer_paper_width: int = 42

    drawer_pin: int = 2
    drawer_pulse_on_ms: int = 120
    drawer_pulse_off_ms: int = 240

    print_test_on_startup: bool = True
    tray_icon_enabled: bool = True
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
