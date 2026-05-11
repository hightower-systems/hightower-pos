# Changelog

All notable changes to hightower-pos.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses semantic versioning.

## [1.0.0] — 2026-05-11

### Added

**Till sessions (open / close shift)** — per-cashier till tracking
with denomination-counting open and close, real-time variance, and a
PDF close report. Closes the deferred shift-management item from the
Monday MVP plan.

- `till_sessions` table + partial unique index that allows at most one
  OPEN session per cashier (alembic mig `0004`).
- `pos_transactions.till_session_id` nullable FK; cash sales and cash
  refunds during the open session update running tallies.
- New endpoints under `/api/till`:
  - `POST /open` — open a session with a denomination count
  - `GET /current` — running tallies + live expected_closing
  - `POST /close` — variance-tolerant close, generates a PDF
  - `GET /sessions/{id}/pdf` — streams the close-report PDF inline
  - `GET /sessions` — admin reporting list with filters
    (`cashier_id`, `status`, `from`, `to`, `limit`, `offset`)
  - `GET /sessions/{id}/transactions` — every txn stamped with this
    session id, for variance investigation
- Refund-attribution rule: refunds attribute to the shift that
  PROCESSES them, not the shift of the original sale. Cash refunds
  during an open shift decrement that shift's expected_closing.
- Close-report PDF: reportlab-rendered one-page letter format, bucketed
  on disk by close month at `{till_pdf_root}/YYYY/MM/{session_id}.pdf`.
  Synchronous render on close; regenerable on demand from the session
  row if the file goes missing. Page-fit guard catches layout overflow
  at test time.
- React UI:
  - `OpenTillModal` blocks the register screen until the cashier opens
    a till (with live total of the denomination grid).
  - `CloseTillModal` with live variance display: green BALANCED, yellow
    within ±$5, red beyond. Submit pops a confirmation when variance
    exceeds $10 — friction at a likely-error threshold, not a block.
    Successful close shows a Print Report + Sign Out screen so the
    PDF opens on the cashier's gesture (popup-blocker safe).
  - StatusStrip header surfaces `Till: $X.XX open` and a Close Till
    button while a session is active.
  - Login response includes the current open till session; logout
    surfaces a warning when a till is still open but does not block.

**User management** — admin CRUD over POS cashiers with self-protective
rules and a Settings UI that doubles as the till-sessions admin view.

- `/api/admin/users` endpoints: `GET` list, `POST` create (initial
  password forced-change on first login), `DELETE /{username}` soft
  delete, `POST /{username}/reset-password`. Cannot deactivate self
  or the last active user; cannot reset own password from this
  surface (use `/api/auth/change-password`).
- Existing `get_auth` already rechecks `is_active`, so deactivating a
  user invalidates their open session on the next request.
- React `SettingsScreen` accessible from the StatusStrip header, with
  two tabs:
  - **Users** — table with active/inactive badges, "Pwd change
    required" hint, per-row Reset Pwd + Deactivate buttons. Self-row
    hides destructive actions. New User modal with name + display
    name + initial password.
  - **Till Sessions** — the admin reporting view from above, with a
    Closed/Open/All filter and a per-row PDF link.

**Customer create-on-no-match** — when the Fabric lookup returns no
match, the attach-customer modal now offers:

- **Attach Existing Customer** (when a match was found)
- **Attach As Typed** (preserve the old behavior — unregistered
  ride-along on the sale, no Fabric record)
- **Create Customer** (POSTs to a new `POST /api/customers` route that
  calls Fabric to register the customer, then attaches the new
  `customer_id` with `registered=true`)

Mock-mode `FabricClient.create_customer` returns a synthetic
`customer_id` so dev boxes exercise the full flow without Fabric
credentials.

**Bookmarks** — color tagging on saved SKUs:

- Each bookmark card has a 3px wraparound border in the chosen color
  (8-step palette: none, red, orange, yellow, green, blue, indigo,
  violet). Card body matches cart-line hierarchy: item name as the
  primary title (`text-sm font-bold`), SKU demoted to a `text-[10px]`
  monospace subtitle.
- Cycle controls in two places, both wired to the same store:
  - Top-left corner swatch button on each bookmark card
  - Inline color-dot button next to the Saved badge on the cart line
- Persists in localStorage. Existing bookmarks load without migration
  (the color field is optional, missing reads as `none`).

### Changed

- **Top bar is now Hightower red** (`#8e2716` brand-red). Both the
  cashier register's StatusStrip and the Settings header switch from
  slate-900 to brand-red, with cream-tinted text/buttons (border/40 +
  bg/10) so contrast holds against the red. Status dots keep
  green/red semantics — those signal Sentry/Windcave health, not
  branding.
- **Cart line hierarchy**: item name is now the primary title
  (`text-lg font-bold`), SKU drops to a smaller monospace subtitle.
- **Cart-line badges** (WH, BIN, Split, Saved, oversold) bumped from
  `text-[10px] px-2 py-0.5` to `text-xs font-semibold px-2.5 py-1` for
  larger touch targets and better legibility.
- **Logout response shape**: `{logged_out, warning?, session_id?}`
  replaces the prior `{ok}`. Warning fires when the cashier still has
  an open till at logout; logout itself is never blocked.
- **`UserInfo` schema**: `till_session: TillSessionBrief | null` added
  so login + `/me` can route the register screen.

### Fixed

- v1.10 attach-customer modal showed no clear path for "this customer
  isn't in Fabric yet" — the prior "Attach as new" wording was
  ambiguous about whether a record was being created. Now explicit.
- PDF was force-downloaded into `~/Downloads` and a popup-blocker
  swallowed the new-tab attempt. Fixed by serving the PDF with
  `Content-Disposition: inline` and switching from a deferred
  `window.open()` to a real `<a target="_blank">` link the cashier
  clicks themselves.
- Close-report PDF subtotal rules were drawn 4pt above the next
  text baseline, slicing through "Opening float" / "Counted" /
  "Expected closing" / "Actual closing" / "VARIANCE". Reflowed.
- Bookmark color tag was invisible in the unset state (`bg-surface-border`
  matched the card border). Now a 3px wraparound border with a
  discoverable top-left corner swatch.

### Documentation

- `docs/cashier-runbook.md` — open/close till flow, variance bands,
  refund-attribution rule, manual-Windcave-Payline refund
  limitation, admin GET surface for managers.

### Database

- New table `till_sessions` (alembic `0004_till_sessions`).
- New column `pos_transactions.till_session_id` (alembic `0004`).
- Both forward-only and additive. Existing rows backfill as NULL /
  unattributed; existing transactions surface in reports as not
  attributed to a shift, which matches reality.

### Dependencies

- `reportlab>=4.0` added for PDF generation.

---

## [0.1.0]

Monday MVP (pre-1.0 internal). Cart build with multi-warehouse /
multi-bin routing, card payment via Windcave HIT, cash payment with
drawer kick, receipt printing, SO creation in Sentry, idempotency
end-to-end, pre-flight cart validation, refunds in a 90-day window,
cashier login, local SQLite price table.
