import logging
import threading
from collections.abc import Callable

from PIL import Image, ImageDraw

from print_agent import __version__

log = logging.getLogger(__name__)


def make_icon_image(*, online: bool = True) -> Image.Image:
    """Generate a 64x64 status icon. Green when online, red when offline."""
    bg = (32, 130, 79) if online else (160, 50, 50)
    img = Image.new("RGB", (64, 64), color=bg)
    draw = ImageDraw.Draw(img)
    draw.rectangle((10, 14, 54, 50), fill=(255, 255, 255))
    draw.rectangle((10, 14, 54, 22), fill=bg)
    draw.line((16, 30, 48, 30), fill=bg, width=2)
    draw.line((16, 36, 48, 36), fill=bg, width=2)
    draw.line((16, 42, 40, 42), fill=bg, width=2)
    return img


def status_text(printer_online: bool) -> str:
    return "Printer: online" if printer_online else "Printer: offline"


def build_tray_icon(
    *,
    printer_online_getter: Callable[[], bool],
    on_test_print: Callable[[], None],
    on_reconnect: Callable[[], None],
    on_quit: Callable[[], None],
):
    """Construct a pystray Icon. Imported lazily so the agent can boot on
    headless CI runners where pystray's platform backend isn't available."""
    import pystray  # noqa: PLC0415  -- intentionally lazy

    def _status_label(_item) -> str:
        return status_text(printer_online_getter())

    def _test_print(icon, _item) -> None:
        try:
            on_test_print()
        except Exception:
            log.exception("tray test-print failed")

    def _reconnect(icon, _item) -> None:
        try:
            on_reconnect()
        except Exception:
            log.exception("tray reconnect failed")

    def _quit(icon, _item) -> None:
        try:
            on_quit()
        finally:
            icon.stop()

    icon = pystray.Icon(
        "hightower-pos-print-agent",
        make_icon_image(online=True),
        f"Hightower POS Print Agent v{__version__}",
        menu=pystray.Menu(
            pystray.MenuItem(_status_label, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Test print", _test_print),
            pystray.MenuItem("Reconnect printer", _reconnect),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", _quit),
        ),
    )
    return icon


def run_in_thread(icon) -> threading.Thread:
    """Run the tray icon's event loop on a daemon thread. The main thread
    keeps running uvicorn; the tray exits with the process."""
    t = threading.Thread(target=icon.run, name="tray-icon", daemon=True)
    t.start()
    return t
