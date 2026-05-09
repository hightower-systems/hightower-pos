import logging
from threading import Lock
from typing import Any, Protocol

log = logging.getLogger(__name__)


class _PrinterDriver(Protocol):
    """Subset of python-escpos's Usb printer that we depend on."""

    def text(self, text: str) -> None: ...
    def cut(self, mode: str = "PART") -> None: ...
    def cashdraw(self, pin: int) -> None: ...
    def is_online(self) -> bool: ...
    def close(self) -> None: ...


class StarTSP100:
    """Wrapper around a python-escpos USB printer that serializes access
    behind a lock so concurrent requests don't interleave bytes on the wire,
    and reconnects once on transient USB failures."""

    def __init__(self, driver: _PrinterDriver | None = None, *, reconnect: Any = None):
        self._driver = driver
        self._reconnect = reconnect
        self._lock = Lock()

    @classmethod
    def open_usb(
        cls, *, vendor_id: int, product_id: int, profile: str
    ) -> "StarTSP100":
        from escpos.printer import Usb

        def _connect() -> _PrinterDriver:
            return Usb(vendor_id, product_id, profile=profile)

        instance = cls(_connect(), reconnect=_connect)
        return instance

    @property
    def driver(self) -> _PrinterDriver:
        if self._driver is None:
            raise RuntimeError("printer driver not initialised")
        return self._driver

    def print_text(self, text: str, *, cut: bool = True) -> None:
        with self._lock:
            try:
                self.driver.text(text)
                if cut:
                    self.driver.cut(mode="PART")
            except Exception:
                self._try_reconnect()
                self.driver.text(text)
                if cut:
                    self.driver.cut(mode="PART")

    def open_drawer(self, *, pin: int = 2) -> None:
        with self._lock:
            try:
                self.driver.cashdraw(pin)
            except Exception:
                self._try_reconnect()
                self.driver.cashdraw(pin)

    def is_online(self) -> bool:
        try:
            return bool(self.driver.is_online())
        except Exception:
            return False

    def close(self) -> None:
        if self._driver is None:
            return
        try:
            self._driver.close()
        except Exception:
            log.exception("printer close failed")

    def _try_reconnect(self) -> None:
        if self._reconnect is None:
            raise
        log.warning("printer call failed; attempting reconnect")
        try:
            if self._driver is not None:
                try:
                    self._driver.close()
                except Exception:
                    pass
            self._driver = self._reconnect()
        except Exception:
            log.exception("printer reconnect failed")
            raise
