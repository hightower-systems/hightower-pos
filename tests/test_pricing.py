import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pos_service.models import POSPrice, POSPriceImport, POSUser
from pos_service.services import pricing


def _csv_bytes(rows: list[str]) -> io.BytesIO:
    return io.BytesIO(("\n".join(rows) + "\n").encode("utf-8"))


def test_get_price_cents_returns_none_for_unknown_sku(db: Session) -> None:
    assert pricing.get_price_cents(db, "UNKNOWN") is None


def test_get_price_cents_returns_value_after_seed(db: Session) -> None:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1999))
    db.commit()
    assert pricing.get_price_cents(db, "WIDGET-001") == 1999


def test_import_csv_happy_path(db: Session) -> None:
    f = _csv_bytes(["sku,price", "WIDGET-001,19.99", "FLY-PL-1,2.25", "STICKER-1,0.50"])
    result = pricing.import_csv(
        db, file=f, filename="prices.csv", imported_by="mike", max_rows=5000
    )
    assert result.rows_imported == 3
    assert result.rows_rejected == 0
    assert result.rejected_lines == []
    assert pricing.get_price_cents(db, "WIDGET-001") == 1999
    assert pricing.get_price_cents(db, "FLY-PL-1") == 225
    assert pricing.get_price_cents(db, "STICKER-1") == 50


def test_import_csv_upsert_overwrites_existing_sku(db: Session) -> None:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1000))
    db.commit()
    f = _csv_bytes(["sku,price", "WIDGET-001,19.99"])
    result = pricing.import_csv(
        db, file=f, filename="p.csv", imported_by="mike", max_rows=5000
    )
    assert result.rows_imported == 1
    assert pricing.get_price_cents(db, "WIDGET-001") == 1999


def test_import_csv_does_not_touch_skus_not_in_file(db: Session) -> None:
    db.add(POSPrice(sku="OLD-1", unit_price_cents=500))
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1000))
    db.commit()
    f = _csv_bytes(["sku,price", "WIDGET-001,19.99"])
    pricing.import_csv(db, file=f, filename="p.csv", imported_by="mike", max_rows=5000)
    assert pricing.get_price_cents(db, "OLD-1") == 500
    assert pricing.get_price_cents(db, "WIDGET-001") == 1999


def test_import_csv_bad_header_raises(db: Session) -> None:
    f = _csv_bytes(["item,cost", "WIDGET-001,19.99"])
    with pytest.raises(pricing.PricingError) as exc:
        pricing.import_csv(
            db, file=f, filename="p.csv", imported_by="mike", max_rows=5000
        )
    assert exc.value.code == "bad_header"
    assert db.query(POSPriceImport).count() == 0
    assert pricing.get_price_cents(db, "WIDGET-001") is None


def test_import_csv_too_many_rows_raises_before_any_upsert(db: Session) -> None:
    rows = ["sku,price"] + [f"SKU-{i:05d},1.00" for i in range(11)]
    with pytest.raises(pricing.PricingError) as exc:
        pricing.import_csv(
            db, file=_csv_bytes(rows), filename="p.csv", imported_by="mike", max_rows=10
        )
    assert exc.value.code == "too_many_rows"
    assert pricing.get_price_cents(db, "SKU-00000") is None
    assert db.query(POSPriceImport).count() == 0


def test_import_csv_skips_empty_rows(db: Session) -> None:
    f = _csv_bytes(["sku,price", "WIDGET-001,19.99", "", "FLY-PL-1,2.25", "  ,  "])
    result = pricing.import_csv(
        db, file=f, filename="p.csv", imported_by="mike", max_rows=5000
    )
    assert result.rows_imported == 2
    assert result.rows_rejected == 0


def test_import_csv_rejects_bad_rows_and_keeps_good_ones(db: Session) -> None:
    f = _csv_bytes(
        [
            "sku,price",
            "WIDGET-001,19.99",
            "BAD-PRICE,abc",
            ",4.50",
            "NEG-PRICE,-1.00",
            "MISSING-COL",
            "FLY-PL-1,2.25",
        ]
    )
    result = pricing.import_csv(
        db, file=f, filename="p.csv", imported_by="mike", max_rows=5000
    )
    assert result.rows_imported == 2
    assert result.rows_rejected == 4
    reasons = sorted(r.reason for r in result.rejected_lines)
    assert reasons == ["empty_sku", "missing_columns", "price_negative", "price_not_numeric"]
    assert pricing.get_price_cents(db, "WIDGET-001") == 1999
    assert pricing.get_price_cents(db, "FLY-PL-1") == 225
    assert pricing.get_price_cents(db, "BAD-PRICE") is None


def test_import_csv_trims_whitespace(db: Session) -> None:
    f = _csv_bytes(["sku,price", "  WIDGET-001  ,  19.99  "])
    pricing.import_csv(db, file=f, filename="p.csv", imported_by="mike", max_rows=5000)
    assert pricing.get_price_cents(db, "WIDGET-001") == 1999


def test_import_csv_handles_utf8_bom(db: Session) -> None:
    body = "sku,price\nWIDGET-001,19.99\n".encode("utf-8-sig")
    result = pricing.import_csv(
        db, file=io.BytesIO(body), filename="p.csv", imported_by="mike", max_rows=5000
    )
    assert result.rows_imported == 1
    assert pricing.get_price_cents(db, "WIDGET-001") == 1999


def test_import_csv_rounds_half_up(db: Session) -> None:
    f = _csv_bytes(["sku,price", "ODD-CENT,1.005"])
    pricing.import_csv(db, file=f, filename="p.csv", imported_by="mike", max_rows=5000)
    assert pricing.get_price_cents(db, "ODD-CENT") == 101


def test_import_csv_writes_audit_row_with_capped_rejected_lines(db: Session) -> None:
    rows = ["sku,price"] + [f"BAD-{i:04d},abc" for i in range(150)]
    result = pricing.import_csv(
        db, file=_csv_bytes(rows), filename="p.csv", imported_by="mike", max_rows=5000
    )
    assert result.rows_imported == 0
    assert result.rows_rejected == 150
    assert len(result.rejected_lines) == pricing.REJECTED_LINES_CAP
    audit = db.query(POSPriceImport).filter(POSPriceImport.id == result.import_id).one()
    assert audit.rows_imported == 0
    assert audit.rows_rejected == 150
    assert audit.imported_by == "mike"
    assert audit.filename == "p.csv"
    assert audit.rejected_lines_json is not None


def test_list_prices_returns_seeded_rows(db: Session) -> None:
    db.add(POSPrice(sku="ZEBRA", unit_price_cents=100))
    db.add(POSPrice(sku="ALPHA", unit_price_cents=200))
    db.commit()
    rows = pricing.list_prices(db)
    assert [r.sku for r in rows] == ["ALPHA", "ZEBRA"]


def test_list_prices_search_filters_by_substring(db: Session) -> None:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=100))
    db.add(POSPrice(sku="FLY-PL-1", unit_price_cents=200))
    db.add(POSPrice(sku="WIDGET-002", unit_price_cents=300))
    db.commit()
    rows = pricing.list_prices(db, search="WIDGET")
    assert sorted(r.sku for r in rows) == ["WIDGET-001", "WIDGET-002"]


def _login_admin(client: TestClient, admin: POSUser) -> None:
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert r.status_code == 200


def _login_cashier(client: TestClient, cashier: POSUser) -> None:
    r = client.post(
        "/api/auth/login", json={"username": "mike", "password": "supersecret"}
    )
    assert r.status_code == 200


def test_post_import_requires_auth(client: TestClient) -> None:
    files = {"file": ("p.csv", b"sku,price\nWIDGET-001,1.00\n", "text/csv")}
    r = client.post("/api/prices/import", files=files)
    assert r.status_code == 401


def test_post_import_blocked_when_admin_has_must_change_password(
    client: TestClient, admin: POSUser
) -> None:
    _login_admin(client, admin)
    files = {"file": ("p.csv", b"sku,price\nWIDGET-001,1.00\n", "text/csv")}
    r = client.post("/api/prices/import", files=files)
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "password_change_required"


def test_post_import_happy_path(client: TestClient, cashier: POSUser) -> None:
    _login_cashier(client, cashier)
    files = {"file": ("p.csv", b"sku,price\nWIDGET-001,19.99\n", "text/csv")}
    r = client.post("/api/prices/import", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["rows_imported"] == 1
    assert body["rows_rejected"] == 0
    assert body["import_id"] >= 1


def test_post_import_bad_header_400(client: TestClient, cashier: POSUser) -> None:
    _login_cashier(client, cashier)
    files = {"file": ("p.csv", b"item,cost\nA,1.00\n", "text/csv")}
    r = client.post("/api/prices/import", files=files)
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "bad_header"


def test_post_import_too_many_rows_400(
    client: TestClient, cashier: POSUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_cashier(client, cashier)
    rows = ["sku,price"] + [f"SKU-{i},1.00" for i in range(20)]
    body = ("\n".join(rows) + "\n").encode("utf-8")
    files = {"file": ("p.csv", body, "text/csv")}
    # The settings fixture has price_csv_max_rows=5000 by default; override
    # via the FastAPI dependency to test the gate without uploading 5001 rows.
    from pos_service.config import Settings, get_settings

    def _tiny_settings() -> Settings:
        return Settings(
            sentry_base_url="http://sentry.test",
            sentry_api_token="t",
            windcave_base_url="http://windcave.test",
            windcave_user="t",
            windcave_key="t",
            windcave_station="t",
            price_csv_max_rows=5,
            session_secret_key="x" * 32,
            session_ttl_hours=1,
            database_url="sqlite:///:memory:",
            allowed_origins="http://localhost:5173",
        )

    client.app.dependency_overrides[get_settings] = _tiny_settings
    try:
        r = client.post("/api/prices/import", files=files)
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["error"] == "too_many_rows"
    assert body["detail"]["max"] == 5


def test_get_prices_lists_imported_rows(client: TestClient, cashier: POSUser) -> None:
    _login_cashier(client, cashier)
    files = {
        "file": ("p.csv", b"sku,price\nWIDGET-001,19.99\nFLY-PL-1,2.25\n", "text/csv")
    }
    client.post("/api/prices/import", files=files)
    r = client.get("/api/prices")
    assert r.status_code == 200
    skus = [row["sku"] for row in r.json()]
    assert "WIDGET-001" in skus and "FLY-PL-1" in skus


def test_get_price_by_sku(client: TestClient, cashier: POSUser) -> None:
    _login_cashier(client, cashier)
    files = {"file": ("p.csv", b"sku,price\nWIDGET-001,19.99\n", "text/csv")}
    client.post("/api/prices/import", files=files)
    r = client.get("/api/prices/WIDGET-001")
    assert r.status_code == 200
    assert r.json()["unit_price_cents"] == 1999


def test_get_price_by_sku_404(client: TestClient, cashier: POSUser) -> None:
    _login_cashier(client, cashier)
    r = client.get("/api/prices/UNKNOWN")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "price_not_found"


def test_get_imports_returns_recent_audit_rows(
    client: TestClient, cashier: POSUser
) -> None:
    _login_cashier(client, cashier)
    files = {"file": ("p.csv", b"sku,price\nA,1.00\n", "text/csv")}
    client.post("/api/prices/import", files=files)
    r = client.get("/api/prices/imports")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert rows[0]["filename"] == "p.csv"
    assert rows[0]["imported_by"] == "mike"
    assert rows[0]["rows_imported"] == 1
