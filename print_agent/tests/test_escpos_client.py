import pytest

from print_agent.escpos_client import StarTSP100
from print_agent.tests.conftest import FakePrinter


def test_print_text_writes_and_cuts(star: StarTSP100, fake_printer: FakePrinter) -> None:
    star.print_text("hello\n", cut=True)
    assert fake_printer.printed == ["hello\n"]
    assert fake_printer.cuts == ["PART"]


def test_print_text_no_cut(star: StarTSP100, fake_printer: FakePrinter) -> None:
    star.print_text("no cut", cut=False)
    assert fake_printer.printed == ["no cut"]
    assert fake_printer.cuts == []


def test_open_drawer_calls_cashdraw(star: StarTSP100, fake_printer: FakePrinter) -> None:
    star.open_drawer(pin=2)
    assert fake_printer.drawer_kicks == [2]


def test_is_online_proxies_driver(star: StarTSP100, fake_printer: FakePrinter) -> None:
    fake_printer.online = True
    assert star.is_online() is True
    fake_printer.online = False
    assert star.is_online() is False


def test_is_online_returns_false_when_driver_raises(fake_printer: FakePrinter) -> None:
    def boom() -> bool:
        raise RuntimeError("usb gone")

    fake_printer.is_online = boom  # type: ignore[method-assign]
    star = StarTSP100(fake_printer)
    assert star.is_online() is False


def test_print_text_reconnects_on_transient_failure() -> None:
    pool = []

    def make_printer() -> FakePrinter:
        new = FakePrinter()
        pool.append(new)
        return new

    initial = make_printer()
    initial.fail_text_once = True
    star = StarTSP100(initial, reconnect=make_printer)
    star.print_text("hello\n", cut=True)
    assert len(pool) == 2
    assert pool[1].printed == ["hello\n"]
    assert pool[1].cuts == ["PART"]


def test_print_text_propagates_when_no_reconnect() -> None:
    fp = FakePrinter()
    fp.fail_text_always = True
    star = StarTSP100(fp)
    with pytest.raises(RuntimeError):
        star.print_text("nope")


def test_open_drawer_reconnects_on_transient_failure() -> None:
    pool = []

    def make_printer() -> FakePrinter:
        new = FakePrinter()
        pool.append(new)
        return new

    initial = make_printer()
    initial.fail_drawer_once = True
    star = StarTSP100(initial, reconnect=make_printer)
    star.open_drawer(pin=5)
    assert len(pool) == 2
    assert pool[1].drawer_kicks == [5]


def test_close_calls_driver_close(star: StarTSP100, fake_printer: FakePrinter) -> None:
    star.close()
    assert fake_printer.closed is True


def test_close_swallows_driver_errors(fake_printer: FakePrinter) -> None:
    def boom() -> None:
        raise RuntimeError("oops")

    fake_printer.close = boom  # type: ignore[method-assign]
    star = StarTSP100(fake_printer)
    # Should not raise
    star.close()
