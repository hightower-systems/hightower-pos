"""Till close-report PDF generation.

Produces a one-page letter-size PDF matching the spec in
06-till-sessions.md: store header, metadata block (cashier,
terminal, opened/closed/duration), opening denominations, activity
stats, closing denominations, reconciliation math, variance line,
signature block.

File location:
    {settings.till_pdf_root}/{YYYY}/{MM}/{session_id}.pdf

Files are organised by month so a year of nightly closes doesn't
pile into one flat directory.

Failure mode (per till plan guardrail): a reportlab error is
isolated to this module. The close-till service catches it and
leaves pdf_path = None on the session row; the PDF endpoint
regenerates on first request. The close itself still succeeds --
the session is CLOSED in the DB, the cashier can leave, accounting
can pull the PDF later.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas

from pos_service.config import Settings
from pos_service.models import POSUser, TillSession
from pos_service.services.till import DENOMINATIONS

log = logging.getLogger(__name__)


# Pretty-print labels for each denomination key. The same data is
# rendered twice (opening + closing); a separate display label keeps
# the storage-keys ('quarter', 'penny') decoupled from the human
# strings ('25¢', '1¢') the cashier reads.
DENOM_DISPLAY: dict[str, str] = {
    "hundred": "$100",
    "fifty":   "$50",
    "twenty":  "$20",
    "ten":     "$10",
    "five":    "$5",
    "one":     "$1",
    "quarter": "25¢",
    "dime":    "10¢",
    "nickel":  "5¢",
    "penny":   "1¢",
}


def session_pdf_path(root: str | Path, session: TillSession) -> Path:
    """Compute the on-disk PDF path for a given session.

    Bucketed by close month rather than open month so a session that
    spans midnight lands in the month its books reflect. Falls back
    to opened_at when closed_at is null (defensive; close always
    populates it).
    """
    when = session.closed_at or session.opened_at
    return (
        Path(root)
        / f"{when.year:04d}"
        / f"{when.month:02d}"
        / f"{session.id}.pdf"
    )


def _format_cents(cents: int) -> str:
    """Cents -> '$1,234.56' or '-$5.50'. Signed because variance is
    signed; opening / counted / expected never are."""
    negative = cents < 0
    cents = abs(cents)
    dollars, rem = divmod(cents, 100)
    formatted = f"${dollars:,}.{rem:02d}"
    return f"-{formatted}" if negative else formatted


def _format_duration(opened: datetime, closed: datetime) -> str:
    delta = closed - opened
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _variance_label(variance_cents: int) -> str:
    if variance_cents == 0:
        return "BALANCED"
    if variance_cents > 0:
        return f"OVER  {_format_cents(variance_cents)}"
    return f"SHORT {_format_cents(variance_cents)}"


def render_close_report(
    session: TillSession,
    user: POSUser,
    *,
    settings: Settings,
) -> Path:
    """Render the close-report PDF for a CLOSED session.

    Returns the absolute path on disk. Caller is responsible for
    storing it in TillSession.pdf_path (so a re-render produces the
    same path -- session_pdf_path is deterministic from session.id +
    closed_at).

    Raises only on truly exceptional conditions (disk full, ReportLab
    bug). The close-till caller wraps this in try/except so the
    session row commits even if the PDF fails.
    """
    if session.status != "CLOSED":
        raise ValueError(
            f"render_close_report requires CLOSED session, got {session.status!r}"
        )
    if (
        session.closed_at is None
        or session.expected_closing_cents is None
        or session.closing_count_cents is None
        or session.variance_cents is None
        or session.closing_denominations_json is None
    ):
        raise ValueError("CLOSED session missing one of the close-time fields")

    opening_counts: dict[str, int] = json.loads(session.opening_denominations_json)
    closing_counts: dict[str, int] = json.loads(session.closing_denominations_json)

    out_path = session_pdf_path(settings.till_pdf_root, session)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    c = Canvas(str(out_path), pagesize=letter)
    width, height = letter

    # Layout uses absolute positioning so the doc spec's column
    # alignment (denomination label | count | subtotal | rule | total)
    # holds across reportlab versions.
    margin_left = 0.75 * inch
    right_margin = width - 0.75 * inch
    y = height - 0.75 * inch

    def text(x: float, y_: float, s: str, *, font: str = "Helvetica",
             size: int = 10) -> None:
        c.setFont(font, size)
        c.drawString(x, y_, s)

    def text_right(x: float, y_: float, s: str, *, font: str = "Courier",
                   size: int = 10) -> None:
        c.setFont(font, size)
        c.drawRightString(x, y_, s)

    def hr_label(y_: float, label: str) -> float:
        """Section divider with a centered label. Returns the y
        coordinate immediately below the divider."""
        c.setStrokeColorRGB(0.4, 0.4, 0.4)
        c.setLineWidth(0.5)
        c.line(margin_left, y_, right_margin, y_)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        text_w = c.stringWidth(label, "Helvetica-Bold", 9)
        c.drawString((width - text_w) / 2, y_ - 12, label)
        c.setFillColorRGB(0, 0, 0)
        return y_ - 24

    # Store header
    text(margin_left, y, settings.store_name or "AvidMax",
         font="Helvetica-Bold", size=14)
    y -= 16
    if settings.store_address_line_1:
        text(margin_left, y, settings.store_address_line_1)
        y -= 12
    if settings.store_address_line_2:
        text(margin_left, y, settings.store_address_line_2)
        y -= 12
    if settings.store_phone:
        text(margin_left, y, settings.store_phone)
        y -= 12
    y -= 8

    # Title
    text(margin_left, y, "TILL CLOSE REPORT", font="Helvetica-Bold", size=14)
    y -= 24

    # Metadata block
    metadata = [
        ("Cashier:", f"{user.display_name} ({user.username})"),
        ("Terminal:", session.terminal_id),
        ("Opened:", session.opened_at.strftime("%Y-%m-%d %H:%M:%S")),
        ("Closed:", session.closed_at.strftime("%Y-%m-%d %H:%M:%S")),
        ("Duration:", _format_duration(session.opened_at, session.closed_at)),
        ("Session ID:", session.id),
    ]
    for label, value in metadata:
        text(margin_left, y, label, font="Helvetica-Bold")
        text(margin_left + 1.2 * inch, y, value, font="Courier")
        y -= 14
    y -= 8

    def denomination_block(counts: dict[str, int]) -> int:
        """Render one denomination grid. Mutates module-level y via
        closure. Returns the total cents of the rendered block so
        the caller can emit a 'Total: $X' line below."""
        nonlocal y
        total = 0
        for name, value_cents in DENOMINATIONS:
            qty = int(counts.get(name, 0))
            subtotal = qty * value_cents
            total += subtotal
            text(margin_left, y, DENOM_DISPLAY[name], font="Courier")
            text(margin_left + 1.0 * inch, y, f"x {qty}", font="Courier")
            text_right(right_margin, y, _format_cents(subtotal))
            y -= 12
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.5)
        c.line(right_margin - 1.2 * inch, y + 4, right_margin, y + 4)
        return total

    # OPENING
    y = hr_label(y, "OPENING")
    denomination_block(opening_counts)
    text(margin_left, y, "Opening float", font="Helvetica-Bold")
    text_right(right_margin, y, _format_cents(session.opening_float_cents),
               font="Courier-Bold")
    y -= 24

    # ACTIVITY
    y = hr_label(y, "ACTIVITY")
    activity_rows = [
        ("Transactions:", str(session.transaction_count)),
        ("Cash transactions:", str(session.cash_transaction_count)),
        ("Cash sales:", _format_cents(session.cash_sales_cents)),
        ("Cash refunds:", _format_cents(session.cash_refunds_cents)),
    ]
    for label, value in activity_rows:
        text(margin_left, y, label)
        text_right(right_margin, y, value, font="Courier")
        y -= 14
    y -= 8

    # CLOSING
    y = hr_label(y, "CLOSING")
    denomination_block(closing_counts)
    text(margin_left, y, "Counted", font="Helvetica-Bold")
    text_right(right_margin, y, _format_cents(session.closing_count_cents),
               font="Courier-Bold")
    y -= 24

    # RECONCILIATION
    y = hr_label(y, "RECONCILIATION")
    text(margin_left, y, "Opening float")
    text_right(right_margin, y, _format_cents(session.opening_float_cents),
               font="Courier")
    y -= 14
    text(margin_left, y, "+ Cash sales")
    text_right(right_margin, y, _format_cents(session.cash_sales_cents),
               font="Courier")
    y -= 14
    text(margin_left, y, "- Cash refunds")
    text_right(
        right_margin, y, _format_cents(-session.cash_refunds_cents),
        font="Courier",
    )
    y -= 8
    c.setStrokeColorRGB(0, 0, 0)
    c.line(right_margin - 1.2 * inch, y + 4, right_margin, y + 4)
    y -= 6
    text(margin_left, y, "Expected closing", font="Helvetica-Bold")
    text_right(
        right_margin, y, _format_cents(session.expected_closing_cents),
        font="Courier-Bold",
    )
    y -= 14
    text(margin_left, y, "Actual closing", font="Helvetica-Bold")
    text_right(
        right_margin, y, _format_cents(session.closing_count_cents),
        font="Courier-Bold",
    )
    y -= 8
    c.line(right_margin - 1.2 * inch, y + 4, right_margin, y + 4)
    y -= 8
    text(margin_left, y, "VARIANCE", font="Helvetica-Bold", size=11)
    text_right(
        right_margin, y, _variance_label(session.variance_cents),
        font="Courier-Bold", size=11,
    )
    y -= 28

    # SIGNATURE
    y = hr_label(y, "SIGNATURE")
    text(margin_left, y, "Cashier signature:", font="Helvetica-Bold")
    c.line(margin_left + 1.6 * inch, y - 2, right_margin, y - 2)
    y -= 28
    text(margin_left, y, "Date:", font="Helvetica-Bold")
    c.line(margin_left + 1.6 * inch, y - 2, right_margin, y - 2)

    c.showPage()
    c.save()
    return out_path
