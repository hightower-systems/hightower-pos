import { useEffect, useState } from "react";

import {
  fetchCheckoutStatus,
  useCancelCheckout,
  useChargeCash,
} from "../api/checkout";
import { formatCents } from "../store/cart";
import { useCheckout } from "../store/checkout";
import { Modal } from "./Modal";

function parseCents(input: string): number | null {
  const trimmed = input.trim();
  if (!trimmed) return null;
  const dollars = Number(trimmed);
  if (!Number.isFinite(dollars) || dollars < 0) return null;
  return Math.round(dollars * 100);
}

export function CashTenderModal() {
  const phase = useCheckout((s) => s.phase);
  const transactionId = useCheckout((s) => s.transactionId);
  const totalCents = useCheckout((s) => s.totalCents);
  const finished = useCheckout((s) => s.finished);
  const reset = useCheckout((s) => s.reset);
  const charge = useChargeCash();
  const cancel = useCancelCheckout();
  const [input, setInput] = useState("");

  const isOpen = phase === "tendering_cash" && transactionId !== null;

  useEffect(() => {
    if (isOpen) setInput("");
  }, [isOpen]);

  const tenderedCents = parseCents(input);
  const sufficient =
    tenderedCents !== null && tenderedCents >= totalCents && totalCents > 0;
  const change =
    tenderedCents !== null ? Math.max(0, tenderedCents - totalCents) : 0;

  function handleQuick(cents: number) {
    setInput((cents / 100).toFixed(2));
  }

  async function handleTender() {
    if (!sufficient || tenderedCents === null || !transactionId) return;
    try {
      await charge.mutateAsync({
        transactionId,
        amount_tendered_cents: tenderedCents,
      });
      try {
        const status = await fetchCheckoutStatus(transactionId);
        finished(status.status, status.result, null);
      } catch {
        finished(
          "COMPLETE",
          {
            so_id: null,
            windcave_txn_ref: null,
            card_brand: null,
            card_last4: null,
            subtotal_cents: 0,
            tax_cents: 0,
            total_cents: totalCents,
            payment_method: "cash",
            receipt_content: null,
          },
          "Receipt unavailable; payment recorded.",
        );
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not record cash payment.";
      finished("PAYMENT_FAILED", null, message);
    }
  }

  function handleCancel() {
    if (transactionId) {
      cancel.mutate(transactionId, {
        onSettled: () => reset(),
      });
    } else {
      reset();
    }
  }

  if (!isOpen) return null;

  return (
    <Modal open={true} onClose={handleCancel} title="Cash payment">
      <div className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between border-b border-surface-border pb-2 font-mono text-sm uppercase tracking-wider">
          <span className="text-ink-muted">Total due</span>
          <span className="text-2xl font-bold text-brand-red">
            {formatCents(totalCents)}
          </span>
        </div>

        <label className="block">
          <span className="mb-1 block font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted">
            Amount tendered
          </span>
          <input
            type="number"
            step="0.01"
            min="0"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onFocus={(event) => event.target.select()}
            placeholder="0.00"
            autoFocus
            aria-label="Amount tendered"
            className="w-full rounded-card border border-surface-inputBorder bg-surface-input px-3 py-2 text-right font-mono text-2xl font-bold text-ink outline-none focus:border-brand-red"
          />
        </label>

        <div className="flex gap-2">
          {[totalCents, totalCents + 500, totalCents + 1000, totalCents + 2000].map(
            (preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => handleQuick(preset)}
                className="flex-1 rounded-card border border-surface-border bg-surface px-2 py-2 font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted hover:bg-surface-card"
              >
                {formatCents(preset)}
              </button>
            ),
          )}
        </div>

        <div
          data-testid="change-due"
          className={`flex items-baseline justify-between border-t border-surface-border pt-3 font-mono text-sm uppercase tracking-wider ${sufficient ? "text-status-success" : "text-status-warning"}`}
        >
          <span>Change</span>
          <span className="text-2xl font-bold">{formatCents(change)}</span>
        </div>

        {charge.isError && (
          <p
            role="alert"
            className="rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-status-danger"
          >
            {charge.error?.message ?? "Could not record cash payment."}
          </p>
        )}

        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={handleCancel}
            disabled={cancel.isPending || charge.isPending}
            className="flex-1 rounded-card border border-surface-border bg-surface px-4 py-3 font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted hover:bg-surface-card disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleTender}
            disabled={!sufficient || charge.isPending}
            className="flex-1 rounded-card bg-brand-red px-4 py-3 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {charge.isPending ? "Tendering..." : "Tender"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
