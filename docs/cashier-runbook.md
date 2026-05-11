# Cashier Runbook

Operational notes for opening, running, and closing a register shift.
This document is the source of truth for the v1.1.0 till-session
feature; refer back here when the system behavior surprises you.

## Opening your till

1. Sign in. If you have no open till for the day, the **Open Till**
   modal blocks the register until you count your starting cash.
2. Enter the count for each denomination (you can skip rows that
   are zero). The total updates as you type.
3. Click **Open Till**. The header now shows `Till: $X.XX open`
   next to a **Close Till** button.

Starting with an empty drawer (all zeros) is allowed. The drawer
amount you enter is the **opening float** the close report
reconciles against — count carefully.

Only one till can be open per cashier at a time. If you try to
open a second, the system refuses with `already_open` and points at
the existing session.

## During the shift

Card sales and cash sales both attribute to your open till. The
header label stays put; the running totals update behind the scenes.

## Refund attribution

**Refunds attribute to the shift that PROCESSES them, not the shift
that made the original sale.**

A refund for yesterday's $50 sale, processed today, decrements
today's expected closing by $50. This matches standard retail
practice and avoids reopening closed shifts to retroactively adjust
their books.

If your variance ever surprises you, check whether any refunds
processed today were for sales from earlier shifts — they'll show
up in the per-session transaction view but not in your own cash
sales total.

## Closing your till

1. Click **Close Till** in the header.
2. Count every bill and coin in the drawer. The reconciliation
   panel on the right shows:
   - Opening float
   - + Cash sales during your shift
   - − Cash refunds during your shift
   - = **Expected** closing
   - The **Counted** total updates live as you type
   - **Variance** shows BALANCED, OVER $X.XX, or SHORT −$X.XX

### Variance colors

- **Green BALANCED** — counted matches expected exactly.
- **Yellow** — variance within ±$5. Likely a rounding or coin-
  counting error; still worth a recount but not alarming.
- **Red** — variance beyond ±$5. Recount before submitting.

### Large variance confirmation

If your variance is more than $10 over or short, clicking **Close
Till** pops a confirmation: "Your variance is $X. Is this correct?
You can recount before closing." Choose **Recount** to go back to
the counting screen, or **Yes, close with this variance** to submit
anyway.

The close is **never blocked** by variance amount — the system
records the variance, generates the report PDF, and lets the
manager / accounting team handle reconciliation offline. Cashiers
who feel pressured to "make it balance" by fudging counts produce
worse books than honest variances, so the system trusts the count
you submit.

### Print the report

After a successful close, the system shows a summary screen with
the variance and two buttons:

- **Print Report** — opens the close-report PDF in a new browser
  tab. Hit **Ctrl+P** (or **⌘+P** on Mac) to print to your local
  printer, or save it to your books folder.
- **Sign Out** — signs you out and clears your session.

If you skip the print step, you can still pull the PDF later: any
signed-in user can fetch it from the Till Sessions admin view (see
below). The PDF lives on disk at
`/data/till_pdfs/YYYY/MM/<session_id>.pdf` (production) or
`./till_pdfs/...` (dev) — the system regenerates it on demand if
the file ever goes missing.

## Signing out with an open till

If you click **Sign Out** while your till is still open, the system
warns: *"You have an open till. Sign out anyway? You'll need to
close it next time you log in."* Click OK to sign out, Cancel to
stay and close properly.

The warning does **not** block sign-out. If you sign out with an
open till, the session stays OPEN in the database. Your next login
will surface that session in the **Open Till** modal — actually, it
won't show the modal at all, because there's already a till open
for you. You can close it from the header **Close Till** button as
usual.

## Limitations

- **Manual refunds via Windcave Payline are NOT reflected in till
  math.** If you process a card refund outside the in-app refund
  flow (using the Windcave Payline portal directly), the till's
  `cash_refunds_cents` won't reflect it and the variance will look
  off by the refund amount. Keep a paper log of any out-of-band
  refunds for the accountant.
- **Single register per cashier per day.** If two cashiers share a
  register, each must open their own till before ringing sales —
  the attribution columns track *who* rang each transaction.
- **Closed sessions are append-only.** If you discover an error
  after closing, the correction lives in accounting, not in the
  till record. The till row is the canonical history of what the
  cashier counted that day.

## Admin view (managers)

Any signed-in user can list and inspect closed sessions via the
admin API today (a Settings UI page will land alongside the user-
management feature):

```
GET /api/till/sessions
GET /api/till/sessions?cashier_id=mike
GET /api/till/sessions?status=OPEN
GET /api/till/sessions?from=2026-05-01&to=2026-05-31
GET /api/till/sessions/{id}/transactions
GET /api/till/sessions/{id}/pdf
```

Use these for end-of-month reports, variance investigation ("show
me every cash sale during the 8 AM Tuesday shift"), or pulling a
lost PDF.
