import pytest
from sqlalchemy import create_engine, text

from pos_service.clients import fabric
from pos_service.clients.fabric import FabricClient, FabricClientError
from pos_service.config import Settings


def test_mock_mode_when_connection_string_empty():
    client = FabricClient(connection_string="")
    assert client.is_mock is True
    assert client.fetch_price_catalog() == []


def test_mock_mode_dispose_is_noop():
    client = FabricClient(connection_string="")
    client.dispose()
    assert client.is_mock is True


def test_from_settings_threads_through_config():
    settings = Settings(
        fabric_connection_string="",
        fabric_query_timeout_s=42,
    )
    client = FabricClient.from_settings(settings)
    assert client.is_mock is True
    assert client._query_timeout_s == 42


def test_from_settings_with_connection_string_constructs_engine(tmp_path):
    db_path = tmp_path / "fabric_stub.sqlite"
    settings = Settings(fabric_connection_string=f"sqlite:///{db_path}")
    client = FabricClient.from_settings(settings)
    try:
        assert client.is_mock is False
        assert client._engine is not None
    finally:
        client.dispose()


def test_fetch_price_catalog_parses_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "fabric_stub.sqlite"
    seed_engine = create_engine(f"sqlite:///{db_path}")
    with seed_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE catalog ("
                "sku TEXT PRIMARY KEY, "
                "unit_price_cents INTEGER NOT NULL"
                ")"
            )
        )
        conn.execute(
            text("INSERT INTO catalog (sku, unit_price_cents) VALUES (:sku, :p)"),
            [
                {"sku": "ROD-100", "p": 19999},
                {"sku": "REEL-200", "p": 24500},
                {"sku": "LINE-300", "p": 1499},
            ],
        )
    seed_engine.dispose()

    monkeypatch.setattr(fabric, "PRICE_CATALOG_QUERY", "SELECT sku, unit_price_cents FROM catalog")
    client = FabricClient(connection_string=f"sqlite:///{db_path}")
    try:
        rows = client.fetch_price_catalog()
    finally:
        client.dispose()

    assert sorted(rows) == [
        ("LINE-300", 1499),
        ("REEL-200", 24500),
        ("ROD-100", 19999),
    ]
    assert all(isinstance(sku, str) and isinstance(cents, int) for sku, cents in rows)


def test_fetch_price_catalog_wraps_engine_errors(tmp_path, monkeypatch):
    db_path = tmp_path / "fabric_stub.sqlite"
    create_engine(f"sqlite:///{db_path}").dispose()

    monkeypatch.setattr(
        fabric, "PRICE_CATALOG_QUERY", "SELECT sku, unit_price_cents FROM nonexistent_table"
    )
    client = FabricClient(connection_string=f"sqlite:///{db_path}")
    try:
        with pytest.raises(FabricClientError, match="price catalog fetch failed"):
            client.fetch_price_catalog()
    finally:
        client.dispose()


def test_fetch_price_catalog_returns_empty_for_empty_catalog(tmp_path, monkeypatch):
    db_path = tmp_path / "fabric_stub.sqlite"
    seed_engine = create_engine(f"sqlite:///{db_path}")
    with seed_engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE catalog (sku TEXT, unit_price_cents INTEGER)")
        )
    seed_engine.dispose()

    monkeypatch.setattr(fabric, "PRICE_CATALOG_QUERY", "SELECT sku, unit_price_cents FROM catalog")
    client = FabricClient(connection_string=f"sqlite:///{db_path}")
    try:
        assert client.fetch_price_catalog() == []
    finally:
        client.dispose()
