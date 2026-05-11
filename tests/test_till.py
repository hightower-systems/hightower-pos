"""Phase 1 till-session backend tests.

Coverage targets are the explicit list in 06-till-sessions.md plus
the integration points the till service hooks into checkout/refund.
PDF endpoint behavior in Phase 1 is the 503 placeholder; Phase 2
tests will assert real file content.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pos_service.models import POSTransaction, POSUser, TillSession
from pos_service.services import till as till_service


def _full_opening() -> dict[str, int]:
    """Sample opening denominations: $237.50 by the doc's example.

    hundred 0 + fifty 1 + twenty 5 + ten 4 + five 6 + one 20
      = 50 + 100 + 40 + 30 + 20 = 240
    quarter 40 + dime 30 + nickel 20 + penny 50
      = 10 + 3 + 1 + 0.50 = 14.50
    actually 240 + 14.50 -- wait: hundred=0, fifty=$50, twenty=$100,
    ten=$40, five=$30, one=$20 -> $240
    quarter=$10, dime=$3, nickel=$1, penny=$0.50 -> $14.50
    total = $254.50? Let me recompute against doc:
      hundred*0=0 + fifty*1=50 + twenty*5=100 + ten*4=40 + five*6=30
      + one*20=20 = 240
      quarter*40=10 + dime*30=3 + nickel*20=1 + penny*50=0.50 = 14.50
      grand total = 254.50, NOT the doc's 237.50.
    Doc has a counting error -- the math at the top of the doc says
    $237.50 but the numbers add to $254.50. Use the right total here;
    Phase 2 PDF test will surface any mismatch with reportlab output.
    """
    return {
        "hundred": 0, "fifty": 1, "twenty": 5, "ten": 4, "five": 6,
        "one": 20, "quarter": 40, "dime": 30, "nickel": 20, "penny": 50,
    }


def _opening_total_cents() -> int:
    return 25450  # $254.50


# ---------------------------------------------------------------------------
# Denominations math
# ---------------------------------------------------------------------------

def test_denominations_to_cents_zero() -> None:
    counts = {name: 0 for name, _ in till_service.DENOMINATIONS}
    assert till_service.denominations_to_cents(counts) == 0


def test_denominations_to_cents_doc_example() -> None:
    assert till_service.denominations_to_cents(_full_opening()) == _opening_total_cents()


def test_denominations_tolerates_missing_keys_as_zero() -> None:
    # React may submit only the denominations the cashier touched.
    assert till_service.denominations_to_cents({"twenty": 3}) == 6000


def test_denominations_rejects_unknown_key() -> None:
    with pytest.raises(till_service.TillError) as exc:
        till_service.denominations_to_cents({"two_dollar": 1})
    assert exc.value.code == "invalid_denomination"
    assert exc.value.status_code == 400


def test_denominations_rejects_negative_count() -> None:
    with pytest.raises(till_service.TillError) as exc:
        till_service.denominations_to_cents({"ten": -1})
    assert exc.value.code == "negative_or_non_integer_count"


# ---------------------------------------------------------------------------
# Service: open / close
# ---------------------------------------------------------------------------

def test_open_session_creates_row(db: Session, cashier: POSUser) -> None:
    session = till_service.open_session(
        db,
        cashier_id=cashier.username,
        terminal_id="REG-1",
        opening_denominations=_full_opening(),
    )
    assert session.status == "OPEN"
    assert session.opening_float_cents == _opening_total_cents()
    assert session.cashier_id == cashier.username
    # Opening_denominations is stored verbatim so the PDF renderer
    # has every coin/bill count available, not just the rolled-up total.
    assert json.loads(session.opening_denominations_json) == _full_opening()


def test_open_session_409_when_already_open(
    db: Session, cashier: POSUser
) -> None:
    till_service.open_session(
        db,
        cashier_id=cashier.username,
        terminal_id="REG-1",
        opening_denominations={"hundred": 1},
    )
    with pytest.raises(till_service.TillError) as exc:
        till_service.open_session(
            db,
            cashier_id=cashier.username,
            terminal_id="REG-1",
            opening_denominations={"hundred": 2},
        )
    assert exc.value.code == "already_open"
    assert exc.value.status_code == 409


def test_two_cashiers_can_have_concurrent_open_sessions(
    db: Session, cashier: POSUser, admin: POSUser
) -> None:
    till_service.open_session(
        db, cashier_id=cashier.username, terminal_id="REG-1",
        opening_denominations={"twenty": 5},
    )
    till_service.open_session(
        db, cashier_id=admin.username, terminal_id="REG-2",
        opening_denominations={"twenty": 3},
    )
    # Partial unique index is per-cashier, not global.
    assert till_service.get_open_session(db, cashier.username) is not None
    assert till_service.get_open_session(db, admin.username) is not None


def test_close_session_balanced(db: Session, cashier: POSUser) -> None:
    s = till_service.open_session(
        db, cashier_id=cashier.username, terminal_id="REG-1",
        opening_denominations={"hundred": 1},  # $100
    )
    closed = till_service.close_session(
        db, cashier_id=cashier.username,
        closing_denominations={"hundred": 1},  # $100, no activity
    )
    assert closed.status == "CLOSED"
    assert closed.expected_closing_cents == 10000
    assert closed.closing_count_cents == 10000
    assert closed.variance_cents == 0
    assert closed.closed_at is not None
    assert closed.id == s.id


def test_close_session_short(db: Session, cashier: POSUser) -> None:
    till_service.open_session(
        db, cashier_id=cashier.username, terminal_id="REG-1",
        opening_denominations={"hundred": 1},
    )
    closed = till_service.close_session(
        db, cashier_id=cashier.username,
        closing_denominations={"fifty": 1, "twenty": 2},  # $90, short $10
    )
    assert closed.variance_cents == -1000


def test_close_session_over(db: Session, cashier: POSUser) -> None:
    till_service.open_session(
        db, cashier_id=cashier.username, terminal_id="REG-1",
        opening_denominations={"hundred": 1},
    )
    closed = till_service.close_session(
        db, cashier_id=cashier.username,
        closing_denominations={"hundred": 1, "five": 1},  # $105, over $5
    )
    assert closed.variance_cents == 500


def test_close_session_409_when_none_open(
    db: Session, cashier: POSUser
) -> None:
    with pytest.raises(till_service.TillError) as exc:
        till_service.close_session(
            db, cashier_id=cashier.username,
            closing_denominations={"hundred": 1},
        )
    assert exc.value.code == "no_open_session"


# ---------------------------------------------------------------------------
# Service: attribute_transaction
# ---------------------------------------------------------------------------

def _make_txn(
    db: Session, cashier_id: str, *, payment_method: str, total_cents: int,
    txn_type: str = "sale",
) -> POSTransaction:
    txn = POSTransaction(
        id=f"txn-{cashier_id}-{total_cents}-{txn_type}-{payment_method}",
        status="COMPLETE",
        txn_type=txn_type,
        cart_json="[]",
        subtotal_cents=total_cents,
        tax_cents=0,
        total_cents=total_cents,
        payment_method=payment_method,
        cashier_id=cashier_id,
        terminal_id="REG-1",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def test_attribute_cash_sale_updates_tallies(
    db: Session, cashier: POSUser
) -> None:
    session = till_service.open_session(
        db, cashier_id=cashier.username, terminal_id="REG-1",
        opening_denominations={"hundred": 1},
    )
    txn = _make_txn(db, cashier.username, payment_method="cash", total_cents=2500)
    till_service.attribute_transaction(db, txn)
    db.commit()
    db.refresh(session)
    assert txn.till_session_id == session.id
    assert session.cash_sales_cents == 2500
    assert session.cash_transaction_count == 1
    assert session.transaction_count == 1


def test_attribute_card_sale_stamps_id_only(
    db: Session, cashier: POSUser
) -> None:
    session = till_service.open_session(
        db, cashier_id=cashier.username, terminal_id="REG-1",
        opening_denominations={"hundred": 1},
    )
    txn = _make_txn(db, cashier.username, payment_method="card", total_cents=2500)
    till_service.attribute_transaction(db, txn)
    db.commit()
    db.refresh(session)
    assert txn.till_session_id == session.id
    assert session.cash_sales_cents == 0
    assert session.cash_transaction_count == 0
    assert session.transaction_count == 1  # card counts in overall, not cash


def test_attribute_cash_refund_increments_refunds(
    db: Session, cashier: POSUser
) -> None:
    session = till_service.open_session(
        db, cashier_id=cashier.username, terminal_id="REG-1",
        opening_denominations={"hundred": 1},
    )
    refund = _make_txn(
        db, cashier.username, payment_method="cash",
        total_cents=1500, txn_type="refund",
    )
    till_service.attribute_transaction(db, refund, is_refund=True)
    db.commit()
    db.refresh(session)
    assert session.cash_refunds_cents == 1500
    assert session.cash_sales_cents == 0


def test_close_with_activity_computes_expected_correctly(
    db: Session, cashier: POSUser
) -> None:
    till_service.open_session(
        db, cashier_id=cashier.username, terminal_id="REG-1",
        opening_denominations={"hundred": 1},  # opening $100
    )
    sale = _make_txn(db, cashier.username, payment_method="cash", total_cents=4500)
    refund = _make_txn(
        db, cashier.username, payment_method="cash",
        total_cents=500, txn_type="refund",
    )
    till_service.attribute_transaction(db, sale)
    till_service.attribute_transaction(db, refund, is_refund=True)
    db.commit()

    # Expected = 100 + 45 - 5 = $140. Cashier counts $138, short $2.
    closed = till_service.close_session(
        db, cashier_id=cashier.username,
        closing_denominations={"hundred": 1, "twenty": 1, "ten": 1, "five": 1, "one": 3},
    )
    assert closed.expected_closing_cents == 14000
    assert closed.closing_count_cents == 13800
    assert closed.variance_cents == -200


# ---------------------------------------------------------------------------
# DB partial-unique-index guard (defense in depth on top of service check)
# ---------------------------------------------------------------------------

def test_partial_unique_index_blocks_concurrent_open_at_db(
    db: Session, cashier: POSUser
) -> None:
    """Service-level check is the primary guard; the partial unique
    index is the final guard. A bare INSERT bypassing the service
    layer should still be blocked.
    """
    db.add(TillSession(
        id="s1", cashier_id=cashier.username, terminal_id="REG-1",
        status="OPEN", opening_float_cents=0,
        opening_denominations_json="{}",
    ))
    db.commit()
    db.add(TillSession(
        id="s2", cashier_id=cashier.username, terminal_id="REG-1",
        status="OPEN", opening_float_cents=0,
        opening_denominations_json="{}",
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _login(client: TestClient, username: str = "mike", password: str = "supersecret") -> None:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200


def test_open_endpoint_creates_session(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    r = client.post(
        "/api/till/open",
        json={"opening_denominations": _full_opening()},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["opening_float_cents"] == _opening_total_cents()
    assert "session_id" in body


def test_open_endpoint_409_when_already_open(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    client.post("/api/till/open", json={"opening_denominations": {"hundred": 1}})
    r = client.post(
        "/api/till/open", json={"opening_denominations": {"hundred": 2}}
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "already_open"


def test_current_endpoint_returns_none_with_no_session(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    r = client.get("/api/till/current")
    assert r.status_code == 200
    assert r.json()["status"] == "NONE"


def test_current_endpoint_returns_open_with_session(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    client.post("/api/till/open", json={"opening_denominations": {"hundred": 1}})
    r = client.get("/api/till/current")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OPEN"
    assert body["opening_float_cents"] == 10000
    assert body["expected_closing_cents"] == 10000  # no activity yet


def test_close_endpoint_computes_variance_and_returns_pdf_url(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    client.post("/api/till/open", json={"opening_denominations": {"hundred": 1}})
    r = client.post(
        "/api/till/close",
        json={"closing_denominations": {"fifty": 1, "twenty": 2, "ten": 1}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["variance_cents"] == 0  # 50+40+10 = 100
    assert body["status"] == "CLOSED"
    assert body["pdf_url"].endswith("/pdf")


def test_close_endpoint_409_when_no_open(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    r = client.post(
        "/api/till/close", json={"closing_denominations": {"hundred": 1}}
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "no_open_session"


def test_pdf_endpoint_503_placeholder_after_close(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    client.post("/api/till/open", json={"opening_denominations": {"hundred": 1}})
    closed = client.post(
        "/api/till/close", json={"closing_denominations": {"hundred": 1}}
    ).json()
    r = client.get(closed["pdf_url"])
    # Phase 1 placeholder; Phase 2 will return 200 with the PDF body.
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "pdf_not_yet_implemented"


def test_pdf_endpoint_404_for_unknown_session(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    r = client.get("/api/till/sessions/does-not-exist/pdf")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "session_not_found"


def test_pdf_endpoint_404_for_other_cashiers_session(
    client: TestClient, cashier: POSUser, admin: POSUser, db: Session
) -> None:
    # Set up: admin opens a till; mike (logged in) should not see it.
    db.add(TillSession(
        id="other-cashier-session", cashier_id=admin.username,
        terminal_id="REG-1", status="CLOSED",
        opening_float_cents=0, opening_denominations_json="{}",
        closing_count_cents=0, closing_denominations_json="{}",
        expected_closing_cents=0, variance_cents=0,
    ))
    db.commit()
    _login(client)
    r = client.get("/api/till/sessions/other-cashier-session/pdf")
    # 404 (not 403) so the token can't learn that the session exists.
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Auth integration: login surfaces open till, logout warns
# ---------------------------------------------------------------------------

def test_login_response_no_till_when_none_open(
    client: TestClient, cashier: POSUser
) -> None:
    r = client.post(
        "/api/auth/login",
        json={"username": "mike", "password": "supersecret"},
    )
    assert r.status_code == 200
    assert r.json().get("till_session") is None


def test_login_response_includes_open_till(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    open_body = client.post(
        "/api/till/open", json={"opening_denominations": {"hundred": 1}}
    ).json()
    # Re-fetch /me to verify till_session rides through on session
    # context (login itself sets the cookie before we can re-login).
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["till_session"] is not None
    assert body["till_session"]["session_id"] == open_body["session_id"]
    assert body["till_session"]["status"] == "OPEN"


def test_logout_warns_when_till_is_open(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    opened = client.post(
        "/api/till/open", json={"opening_denominations": {"hundred": 1}}
    ).json()
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    body = r.json()
    assert body["logged_out"] is True
    assert body["warning"] == "open_till_session"
    assert body["session_id"] == opened["session_id"]


def test_logout_no_warning_with_no_till(
    client: TestClient, cashier: POSUser
) -> None:
    _login(client)
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    body = r.json()
    assert body["logged_out"] is True
    assert body.get("warning") is None
