from fastapi.testclient import TestClient

from print_agent.tests.conftest import FakePrinter


def test_print_requires_origin(client: TestClient) -> None:
    r = client.post("/print", json={"format": "text", "content": "x"})
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden_origin"


def test_print_rejects_unknown_origin(client: TestClient) -> None:
    r = client.post(
        "/print",
        json={"format": "text", "content": "x"},
        headers={"Origin": "http://evil.test"},
    )
    assert r.status_code == 403


def test_print_happy_path(
    client: TestClient, fake_printer: FakePrinter, headers: dict
) -> None:
    r = client.post(
        "/print",
        json={"format": "text", "content": "hello\n", "cut": True},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["printer_status"] == "ok"
    assert fake_printer.printed == ["hello\n"]
    assert fake_printer.cuts == ["PART"]


def test_print_with_open_drawer_after(
    client: TestClient, fake_printer: FakePrinter, headers: dict
) -> None:
    r = client.post(
        "/print",
        json={
            "format": "text",
            "content": "cash sale receipt",
            "cut": True,
            "open_drawer_after": True,
        },
        headers=headers,
    )
    assert r.status_code == 200
    assert fake_printer.drawer_kicks == [2]


def test_print_503_when_printer_offline(
    client: TestClient, fake_printer: FakePrinter, headers: dict
) -> None:
    fake_printer.fail_text_always = True
    r = client.post(
        "/print",
        json={"format": "text", "content": "x"},
        headers=headers,
    )
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "printer_offline"


def test_open_drawer_endpoint(
    client: TestClient, fake_printer: FakePrinter, headers: dict
) -> None:
    r = client.post("/open-drawer", headers=headers)
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert fake_printer.drawer_kicks == [2]


def test_status_endpoint_initial_state(
    client: TestClient, headers: dict
) -> None:
    r = client.get("/status", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["agent_status"] == "online"
    assert "agent_version" in body
    assert body["printer_online"] is True
    assert body["last_print_at"] is None


def test_status_reflects_last_print_after_print_call(
    client: TestClient, headers: dict
) -> None:
    client.post(
        "/print",
        json={"format": "text", "content": "x"},
        headers=headers,
    )
    r = client.get("/status", headers=headers)
    assert r.json()["last_print_at"] is not None


def test_status_reports_printer_offline_when_driver_says_so(
    client: TestClient, fake_printer: FakePrinter, headers: dict
) -> None:
    fake_printer.online = False
    r = client.get("/status", headers=headers)
    assert r.json()["printer_online"] is False


def test_test_print_endpoint(
    client: TestClient, fake_printer: FakePrinter, headers: dict
) -> None:
    r = client.post("/test-print", headers=headers)
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert any("Hightower Print Agent" in line for line in fake_printer.printed)


def test_print_format_validation_rejects_unknown_format(
    client: TestClient, headers: dict
) -> None:
    r = client.post(
        "/print",
        json={"format": "image", "content": "x"},
        headers=headers,
    )
    assert r.status_code == 422
