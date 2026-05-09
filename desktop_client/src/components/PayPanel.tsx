import { useState } from "react";

import { useChargeCard, useStartCheckout } from "../api/checkout";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import { computeTotals, formatCents, useCart } from "../store/cart";
import { useCheckout } from "../store/checkout";
import { useCustomer } from "../store/customer";

export function PayPanel() {
  const lines = useCart((s) => s.lines);
  const totals = computeTotals(lines);
  const startedAt = useCheckout((s) => s.startedAt);
  const startedCash = useCheckout((s) => s.startedCash);
  const failed = useCheckout((s) => s.failed);
  const phase = useCheckout((s) => s.phase);
  const attachedCustomer = useCustomer((s) => s.attached);
  const [localError, setLocalError] = useState<string | null>(null);

  const start = useStartCheckout();
  const charge = useChargeCard();

  const isPending = start.isPending || charge.isPending;
  const cartEmpty = lines.length === 0;
  const flowActive = phase !== "idle";
  const canPay = !cartEmpty && !isPending && !flowActive;

  function buildLinesPayload() {
    return lines.map((l) => ({
      sku: l.sku,
      name: l.name,
      warehouse_id: l.warehouse_id,
      bin_id: l.bin_id,
      quantity: l.quantity,
      is_taxable: l.is_taxable,
    }));
  }

  function buildCustomerPayload() {
    if (!attachedCustomer) return undefined;
    return {
      customer_id: attachedCustomer.customer_id,
      name: attachedCustomer.name,
      email: attachedCustomer.email,
      phone: attachedCustomer.phone,
    };
  }

  async function handleCard() {
    setLocalError(null);
    try {
      const startResp = await start.mutateAsync({
        lines: buildLinesPayload(),
        customer: buildCustomerPayload(),
      });
      const chargeResp = await charge.mutateAsync({
        transactionId: startResp.transaction_id,
      });
      startedAt(chargeResp.transaction_id);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not start checkout.";
      setLocalError(message);
      failed(message);
    }
  }

  async function handleCash() {
    setLocalError(null);
    try {
      const startResp = await start.mutateAsync({
        lines: buildLinesPayload(),
        customer: buildCustomerPayload(),
      });
      startedCash(startResp.transaction_id, startResp.total_cents);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not start checkout.";
      setLocalError(message);
      failed(message);
    }
  }

  useKeyboardShortcuts([
    { key: "F1", handler: handleCash, enabled: canPay },
    { key: "F2", handler: handleCard, enabled: canPay },
  ]);

  return (
    <div
      className="flex flex-col gap-2 rounded-card border border-surface-border bg-surface-card p-4"
      aria-label="Pay panel"
    >
      <div className="grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={handleCard}
          disabled={!canPay}
          aria-label="Pay with card"
          className="flex min-h-[64px] flex-col items-center justify-center rounded-card bg-brand-red px-6 py-4 font-mono text-base font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-brand-red focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span className="flex items-center gap-2">
            <kbd className="rounded-badge border border-brand-cream/40 bg-brand-cream/10 px-1.5 py-0.5 text-[9px] font-bold tracking-wider">
              F2
            </kbd>
            Pay Card
          </span>
          <span className="text-xs font-semibold">
            {formatCents(totals.total_cents)}
          </span>
        </button>
        <button
          type="button"
          onClick={handleCash}
          disabled={!canPay}
          aria-label="Pay with cash"
          className="flex min-h-[64px] flex-col items-center justify-center rounded-card border border-brand-red bg-surface px-6 py-4 font-mono text-base font-bold uppercase tracking-wider text-brand-red hover:bg-brand-red/5 focus:outline-none focus:ring-2 focus:ring-brand-red focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span className="flex items-center gap-2">
            <kbd className="rounded-badge border border-brand-red/40 bg-brand-red/5 px-1.5 py-0.5 text-[9px] font-bold tracking-wider">
              F1
            </kbd>
            Pay Cash
          </span>
          <span className="text-xs font-semibold">
            {formatCents(totals.total_cents)}
          </span>
        </button>
      </div>
      {localError && (
        <p
          role="alert"
          className="rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-status-danger"
        >
          {localError}
        </p>
      )}
    </div>
  );
}
