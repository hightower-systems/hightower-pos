import { useMemo, useState } from "react";

import {
  DENOMINATIONS,
  type DenominationCounts,
  denominationsToCents,
  formatCents,
  useCloseTill,
  useCurrentTill,
} from "../api/till";

interface Props {
  open: boolean;
  onClose: () => void;
  // Called when the cashier dismisses the success screen after a
  // successful close. Parent uses this to sign the cashier out --
  // signing them out happens AFTER they've had a chance to open the
  // PDF on their own gesture (avoids popup blockers + accidental
  // dropped-on-the-floor PDFs).
  onDoneAfterClose: () => void;
}

/** Close-till modal with live denomination grid + reconciliation panel.
 *
 * Left side: the same denomination input grid as OpenTillModal.
 * Right side: opening float + running cash sales/refunds (refetched
 * every 30s while the modal is open, per the doc) -> expected
 * closing, with the cashier-entered total ('Counted') and the live
 * VARIANCE computed locally so the cashier sees the delta change as
 * they type.
 *
 * Cancel returns to the register. Submit POSTs to /api/till/close
 * and hands the PDF URL back to the parent (which opens it in a new
 * tab and signs the cashier out). Variance amount is recorded but
 * does NOT block the close per the doc guardrail.
 */
export function CloseTillModal({ open, onClose, onDoneAfterClose }: Props) {
  const [counts, setCounts] = useState<DenominationCounts>({});
  const [error, setError] = useState<string | null>(null);
  // After a successful close, switch to a success screen so the
  // cashier can open the PDF on their own click (popup-blocker safe)
  // and explicitly sign out when they're done. Null = still on the
  // input screen.
  const [closed, setClosed] = useState<
    null | { pdf_url: string; variance_cents: number }
  >(null);
  // Refetch the running tallies every 30s while the modal is open
  // so a late cash sale in another tab (unlikely but possible)
  // doesn't desync the variance preview.
  const current = useCurrentTill(open && closed === null ? 30_000 : undefined);
  const closeTill = useCloseTill();

  const counted = useMemo(() => denominationsToCents(counts), [counts]);
  // Narrow once so the rest of the render can read fields directly
  // without re-checking the discriminator.
  const openSession =
    current.data?.status === "OPEN" ? current.data : null;
  const expected = openSession?.expected_closing_cents ?? 0;
  const variance = counted - expected;

  function setCount(key: string, raw: string) {
    const n = parseInt(raw, 10);
    setCounts((prev) => ({
      ...prev,
      [key]: Number.isFinite(n) && n >= 0 ? n : 0,
    }));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    closeTill.mutate(counts, {
      onSuccess: (response) => {
        setClosed({
          pdf_url: response.pdf_url,
          variance_cents: response.variance_cents,
        });
      },
      onError: (err) => {
        setError(err instanceof Error ? err.message : "Could not close till.");
      },
    });
  }

  if (!open) return null;

  // Success screen: shown after the close commits. Two explicit
  // buttons -- Print Report (opens the PDF in a new tab on the
  // cashier's click, so no popup blocker) and Sign Out (which the
  // parent maps to the auto-logout). Both are user gestures.
  if (closed !== null) {
    return (
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Till Closed"
        data-testid="close-till-success"
        className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4"
      >
        <div className="w-full max-w-md rounded-card border border-surface-border bg-surface p-6 shadow-2xl">
          <h2 className="font-mono text-base font-bold uppercase tracking-wider text-ink">
            Till Closed
          </h2>
          <p className="mt-2 text-sm text-ink-muted">
            Your shift is closed. Print the report for your records, then
            sign out.
          </p>
          <div className="mt-4 rounded-card border border-surface-border bg-surface-card p-4">
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-bold uppercase tracking-wider text-ink">
                Variance
              </span>
              <span className="font-mono text-lg font-bold text-ink">
                {varianceLabel(closed.variance_cents)}
              </span>
            </div>
          </div>
          <div className="mt-5 flex items-center justify-end gap-3">
            <a
              href={closed.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-card border border-surface-border bg-surface px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-ink hover:bg-surface-card"
            >
              Print Report
            </a>
            <button
              type="button"
              onClick={onDoneAfterClose}
              className="rounded-card bg-brand-red px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Close Till"
      data-testid="close-till-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-3xl rounded-card border border-surface-border bg-surface p-6 shadow-2xl"
      >
        <div className="flex items-center justify-between gap-4">
          <h2 className="font-mono text-base font-bold uppercase tracking-wider text-ink">
            Close Till
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cancel close till"
            className="rounded-card border border-surface-border bg-surface px-2 py-1 font-mono text-sm text-ink-muted hover:bg-surface-card"
          >
            ×
          </button>
        </div>

        <p className="mt-2 text-sm text-ink-muted">
          Count all the cash currently in the drawer. Variance updates live.
        </p>

        <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-2">
          {/* Denomination grid (left) */}
          <div>
            <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-ink-muted">
              Denomination count
            </h3>
            <div className="mt-2 grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-2">
              {DENOMINATIONS.map((d) => {
                const qty = counts[d.key] ?? 0;
                return (
                  <div key={d.key} className="contents">
                    <span className="font-mono text-sm font-semibold text-ink">
                      {d.label}
                    </span>
                    <input
                      type="number"
                      min={0}
                      inputMode="numeric"
                      value={qty || ""}
                      onChange={(e) => setCount(d.key, e.target.value)}
                      onFocus={(e) => e.target.select()}
                      aria-label={`Count of ${d.label}`}
                      className="w-20 rounded-card border border-surface-inputBorder bg-surface-input px-2 py-1 text-right font-mono text-sm text-ink outline-none focus:border-brand-red"
                    />
                    <span className="min-w-[80px] text-right font-mono text-sm text-ink-muted">
                      {formatCents(qty * d.cents)}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-surface-border pt-2">
              <span className="font-mono text-sm font-bold uppercase tracking-wider text-ink">
                Total counted
              </span>
              <span
                data-testid="close-till-counted"
                className="font-mono text-lg font-bold text-ink"
              >
                {formatCents(counted)}
              </span>
            </div>
          </div>

          {/* Reconciliation panel (right) */}
          <div className="rounded-card border border-surface-border bg-surface-card p-4">
            <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-ink-muted">
              Reconciliation
            </h3>
            <ReconciliationRow
              label="Opening float"
              value={
                openSession
                  ? formatCents(openSession.opening_float_cents)
                  : "—"
              }
            />
            <ReconciliationRow
              label="+ Cash sales"
              value={
                openSession
                  ? formatCents(openSession.cash_sales_cents)
                  : "—"
              }
            />
            <ReconciliationRow
              label="- Cash refunds"
              value={
                openSession
                  ? formatCents(-openSession.cash_refunds_cents)
                  : "—"
              }
            />
            <div className="my-2 border-t border-surface-border" />
            <ReconciliationRow
              label="Expected"
              value={openSession ? formatCents(expected) : "—"}
              bold
            />
            <ReconciliationRow
              label="Counted"
              value={formatCents(counted)}
              bold
            />
            <div className="my-2 border-t border-surface-border" />
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-bold uppercase tracking-wider text-ink">
                Variance
              </span>
              <span
                data-testid="close-till-variance"
                className="font-mono text-lg font-bold text-ink"
              >
                {varianceLabel(variance)}
              </span>
            </div>
          </div>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-3 rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 font-mono text-xs text-status-danger"
          >
            {error}
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-card border border-surface-border bg-surface px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-ink-muted hover:bg-surface-card"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={closeTill.isPending || !openSession}
            className="rounded-card bg-brand-red px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:opacity-60"
          >
            {closeTill.isPending ? "Closing..." : "Close Till"}
          </button>
        </div>
      </form>
    </div>
  );
}

function ReconciliationRow({
  label,
  value,
  bold = false,
}: {
  label: string;
  value: string;
  bold?: boolean;
}) {
  return (
    <div className="mt-1.5 flex items-center justify-between">
      <span
        className={`text-sm ${bold ? "font-bold text-ink" : "text-ink-muted"}`}
      >
        {label}
      </span>
      <span
        className={`font-mono text-sm ${bold ? "font-bold text-ink" : "text-ink"}`}
      >
        {value}
      </span>
    </div>
  );
}

function varianceLabel(cents: number): string {
  if (cents === 0) return "BALANCED";
  if (cents > 0) return `OVER ${formatCents(cents)}`;
  return `SHORT ${formatCents(cents)}`;
}
