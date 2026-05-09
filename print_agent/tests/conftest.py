from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from print_agent import agent as agent_module
from print_agent.agent import create_app, get_printer, set_printer
from print_agent.config import Settings
from print_agent.escpos_client import StarTSP100


class FakePrinter:
    def __init__(self) -> None:
        self.printed: list[str] = []
        self.cuts: list[str] = []
        self.drawer_kicks: list[int] = []
        self.online: bool = True
        self.fail_text_once: bool = False
        self.fail_drawer_once: bool = False
        self.fail_text_always: bool = False
        self.closed: bool = False

    def text(self, text: str) -> None:
        if self.fail_text_always:
            raise RuntimeError("USB write failed")
        if self.fail_text_once:
            self.fail_text_once = False
            raise RuntimeError("USB write failed (transient)")
        self.printed.append(text)

    def cut(self, mode: str = "PART") -> None:
        self.cuts.append(mode)

    def cashdraw(self, pin: int) -> None:
        if self.fail_drawer_once:
            self.fail_drawer_once = False
            raise RuntimeError("USB write failed (transient)")
        self.drawer_kicks.append(pin)

    def is_online(self) -> bool:
        return self.online

    def close(self) -> None:
        self.closed = True


ALLOWED = "http://pos-vm.local:8080"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        listen_host="127.0.0.1",
        listen_port=9100,
        allowed_origin=ALLOWED,
        printer_vendor_id=0x0519,
        printer_product_id=0x0001,
        printer_profile="TSP100",
        drawer_pin=2,
        print_test_on_startup=False,
    )


@pytest.fixture
def fake_printer() -> FakePrinter:
    return FakePrinter()


@pytest.fixture
def reconnecting_printer(fake_printer: FakePrinter) -> StarTSP100:
    """A StarTSP100 that reconnects to a fresh FakePrinter on failure."""
    pool = [FakePrinter()]

    def _reconnect() -> FakePrinter:
        new = FakePrinter()
        pool.append(new)
        return new

    star = StarTSP100(fake_printer, reconnect=_reconnect)
    star._reconnect_pool = pool  # type: ignore[attr-defined]  # for test assertions
    return star


@pytest.fixture
def star(fake_printer: FakePrinter) -> StarTSP100:
    return StarTSP100(fake_printer)


@pytest.fixture
def client(settings: Settings, star: StarTSP100) -> Generator[TestClient, None, None]:
    app = create_app(settings)
    set_printer(star)
    app.dependency_overrides[get_printer] = lambda: star
    try:
        with TestClient(app) as c:
            yield c
    finally:
        set_printer(None)
        agent_module._last_print_at = None  # type: ignore[attr-defined]


@pytest.fixture
def headers() -> dict[str, str]:
    return {"Origin": ALLOWED}
