"""Till-session domain logic.

Reads:
  - get_open_session(db, cashier_id) -> TillSession | None

Mutations (each in its own transaction; caller commits):
  - open_session(db, cashier_id, terminal_id, opening_denominations)
  - close_session(db, cashier_id, closing_denominations)
  - attribute_transaction(db, txn, *, is_refund=False)

Money math invariants:
  - All amounts in integer cents. The DENOMINATIONS table is the only
    place that knows cent values per coin/bill.
  - expected_closing = opening_float + cash_sales - cash_refunds
  - variance = closing_count - expected_closing
    Positive variance = over; negative = short.

One open session per cashier at a time. Attempting to open a second
returns TillError('already_open'); the DB partial unique index is the
final guard (mig 0004).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from pos_service.models import POSTransaction, TillSession

log = logging.getLogger(__name__)


# Canonical denomination set. Order is largest-first so the PDF and
# React UI render the same top-to-bottom layout (Phase 2 PDF +
# Phase 3 React rely on this order; importing the list directly
# instead of reimplementing it). Cent values are integer; no float.
DENOMINATIONS: list[tuple[str, int]] = [
    ("hundred", 10000),
    ("fifty", 5000),
    ("twenty", 2000),
    ("ten", 1000),
    ("five", 500),
    ("one", 100),
    ("quarter", 25),
    ("dime", 10),
    ("nickel", 5),
    ("penny", 1),
]

DENOMINATION_KEYS = frozenset(name for name, _ in DENOMINATIONS)


class TillError(Exception):
    """Domain error with a stable error_code + http status hint.

    Used by the route layer to translate to JSON shape:
    {"error": <code>, ...details}
    """

    def __init__(
        self,
        code: str,
        status_code: int = 400,
        **details,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.details = details


def denominations_to_cents(counts: dict[str, int]) -> int:
    """Sum a denomination-count dict to total cents.

    Tolerates missing keys (treated as zero) so the React side can
    submit only the denominations the cashier actually entered. An
    unknown key raises -- it's a client bug, not a runtime tolerance
    case. Negative counts raise; you can't have negative bills.
    """
    total = 0
    for key in counts:
        if key not in DENOMINATION_KEYS:
            raise TillError(
                "invalid_denomination",
                status_code=400,
                key=key,
                valid=sorted(DENOMINATION_KEYS),
            )
    for name, value_cents in DENOMINATIONS:
        qty = counts.get(name, 0)
        if not isinstance(qty, int) or qty < 0:
            raise TillError(
                "negative_or_non_integer_count",
                status_code=400,
                key=name,
                value=qty,
            )
        total += qty * value_cents
    return total


def get_open_session(db: Session, cashier_id: str) -> TillSession | None:
    """Return the cashier's current OPEN session, or None.

    The (cashier_id, status='OPEN') partial unique index guarantees
    at most one row, so .first() is the right shape -- no need to
    branch on multiple rows.
    """
    stmt = (
        select(TillSession)
        .where(TillSession.cashier_id == cashier_id)
        .where(TillSession.status == "OPEN")
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def open_session(
    db: Session,
    *,
    cashier_id: str,
    terminal_id: str,
    opening_denominations: dict[str, int],
) -> TillSession:
    """Create an OPEN session for the cashier. 409 if one already open."""
    existing = get_open_session(db, cashier_id)
    if existing is not None:
        raise TillError(
            "already_open",
            status_code=409,
            existing_session_id=existing.id,
        )

    opening_float = denominations_to_cents(opening_denominations)
    session = TillSession(
        id=str(uuid.uuid4()),
        cashier_id=cashier_id,
        terminal_id=terminal_id,
        status="OPEN",
        opening_float_cents=opening_float,
        opening_denominations_json=json.dumps(opening_denominations),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def close_session(
    db: Session,
    *,
    cashier_id: str,
    closing_denominations: dict[str, int],
) -> TillSession:
    """Close the cashier's open session. 409 if none open.

    Variance is recorded but the close is ACCEPTED regardless of
    amount. Per the plan doc guardrail: forcing 'must balance' just
    teaches cashiers to fudge counts. Variance lives in the record
    and the PDF, accounting reconciles offline.
    """
    session = get_open_session(db, cashier_id)
    if session is None:
        raise TillError("no_open_session", status_code=409)

    closing_count = denominations_to_cents(closing_denominations)
    expected = (
        session.opening_float_cents
        + session.cash_sales_cents
        - session.cash_refunds_cents
    )
    variance = closing_count - expected

    session.status = "CLOSED"
    session.closing_denominations_json = json.dumps(closing_denominations)
    session.closing_count_cents = closing_count
    session.expected_closing_cents = expected
    session.variance_cents = variance
    session.closed_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.refresh(session)
    return session


def attribute_transaction(
    db: Session,
    txn: POSTransaction,
    *,
    is_refund: bool = False,
) -> TillSession | None:
    """Stamp till_session_id + update running tallies on the open session.

    Called from checkout / refund finalization at PAYMENT_SUCCESS.
    Caller commits.

    - Card transactions: stamp till_session_id (so the admin
      'all transactions during this shift' view works), increment
      transaction_count, but do not affect cash math.
    - Cash sales: stamp + transaction_count + cash_transaction_count
      + add total_cents to cash_sales_cents.
    - Cash refunds: stamp + transaction_count + cash_transaction_count
      + add (positive) total_cents to cash_refunds_cents.
      Refund txn rows store total_cents as the positive amount being
      handed back to the customer; the till math model
      (expected = opening + sales - refunds) subtracts that amount.

    No open session = the cashier somehow skipped the open-till
    modal (defensive case -- the React client gates the register
    UI on open till). Log loudly and proceed without attribution.
    """
    session = get_open_session(db, txn.cashier_id)
    if session is None:
        log.error(
            "transaction_finalized_with_no_open_till",
            extra={"txn_id": txn.id, "cashier_id": txn.cashier_id},
        )
        return None

    txn.till_session_id = session.id
    session.transaction_count += 1
    if txn.payment_method == "cash":
        session.cash_transaction_count += 1
        if is_refund:
            session.cash_refunds_cents += txn.total_cents
        else:
            session.cash_sales_cents += txn.total_cents
    return session
