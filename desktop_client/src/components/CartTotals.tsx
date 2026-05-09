import { computeTotals, formatCents, useCart } from "../store/cart";

export function CartTotals() {
  const lines = useCart((s) => s.lines);
  const totals = computeTotals(lines);

  return (
    <div
      className="rounded-card border border-surface-border bg-surface-card px-6 py-4"
      aria-label="Cart totals"
    >
      <div className="flex items-baseline justify-between font-mono text-sm uppercase tracking-wider text-ink-muted">
        <span>Subtotal</span>
        <span data-testid="cart-subtotal">{formatCents(totals.subtotal_cents)}</span>
      </div>
      <div className="mt-1 flex items-baseline justify-between font-mono text-sm uppercase tracking-wider text-ink-muted">
        <span>Tax</span>
        <span data-testid="cart-tax">{formatCents(totals.tax_cents)}</span>
      </div>
      <div className="mt-3 flex items-baseline justify-between border-t border-surface-border pt-3 font-mono text-2xl font-bold uppercase tracking-wider text-brand-red">
        <span>Total</span>
        <span data-testid="cart-total">{formatCents(totals.total_cents)}</span>
      </div>
    </div>
  );
}
