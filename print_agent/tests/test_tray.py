"""Unit tests for the tray module's pure helpers.

The pystray Icon itself wires into the platform's tray API and is hard to
exercise headlessly. These tests cover the deterministic pieces: icon
generation and the status-text mapping.
"""
from PIL import Image

from print_agent.tray import make_icon_image, status_text


def test_make_icon_image_online_green() -> None:
    img = make_icon_image(online=True)
    assert isinstance(img, Image.Image)
    assert img.size == (64, 64)
    # Background is the green status colour
    assert img.getpixel((0, 0)) == (32, 130, 79)


def test_make_icon_image_offline_red() -> None:
    img = make_icon_image(online=False)
    assert img.getpixel((0, 0)) == (160, 50, 50)


def test_status_text_online() -> None:
    assert status_text(True) == "Printer: online"


def test_status_text_offline() -> None:
    assert status_text(False) == "Printer: offline"
