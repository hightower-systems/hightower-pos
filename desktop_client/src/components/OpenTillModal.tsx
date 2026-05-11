import { useMemo, useState } from "react";

import {
  DENOMINATIONS,
  type DenominationCounts,
  denominationsToCents,
  formatCents,
  useOpenTill,
} from "../api/till";

interface Props {
  open: boolean;
  onOpened: () => void;
}

/** Blocking modal: cashier counts opening float by denomination,
 * total updates live, submit POSTs to /api/till/open. Empty opening
 * (all zeros) is allowed per the doc -- cashier may start with an
 * empty drawer. No close affordance: this modal stays up until the
 * till is opened. */
export function OpenTillModal({ open, onOpened }: Props) {
  const [counts, setCounts] = useState<DenominationCounts>({});
  const [error, setError] = useState<string | null>(null);
  const openTill = useOpenTill();

  const total = useMemo(() => denominationsToCents(counts), [counts]);

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
    openTill.mutate(counts, {
      onSuccess: () => {
        onOpened();
      },
      onError: (err) => {
        setError(err instanceof Error ? err.message : "Could not open till.");
      },
    });
  }

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Open Till"
      data-testid="open-till-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4"
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-card border border-surface-border bg-surface p-6 shadow-2xl"
      >
        <h2 className="font-mono text-base font-bold uppercase tracking-wider text-ink">
          Open Till
        </h2>
        <p className="mt-2 text-sm text-ink-muted">
          Count the starting cash in your drawer. You can&apos;t ring up sales
          until a till is open.
        </p>

        <div className="mt-4 grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-2">
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

        <div className="mt-4 flex items-center justify-between border-t border-surface-border pt-3">
          <span className="font-mono text-sm font-bold uppercase tracking-wider text-ink">
            Total starting
          </span>
          <span
            data-testid="open-till-total"
            className="font-mono text-lg font-bold text-ink"
          >
            {formatCents(total)}
          </span>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-3 rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 font-mono text-xs text-status-danger"
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={openTill.isPending}
          className="mt-4 w-full rounded-card bg-brand-red px-4 py-3 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:opacity-60"
        >
          {openTill.isPending ? "Opening..." : "Open Till"}
        </button>
      </form>
    </div>
  );
}
