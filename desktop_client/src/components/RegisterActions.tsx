import { useCheckout } from "../store/checkout";
import { useCustomer } from "../store/customer";
import { useRefund } from "../store/refund";

export function RegisterActions() {
  const openLookup = useRefund((s) => s.openLookup);
  const refundPhase = useRefund((s) => s.phase);
  const checkoutPhase = useCheckout((s) => s.phase);
  const customer = useCustomer((s) => s.attached);
  const customerPhase = useCustomer((s) => s.phase);
  const openCustomer = useCustomer((s) => s.openLookup);
  const detachCustomer = useCustomer((s) => s.detach);

  const flowActive =
    refundPhase !== "idle" || checkoutPhase !== "idle";
  const refundDisabled = flowActive;
  const customerActionDisabled = flowActive || customerPhase === "lookup";

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {customer ? (
        <span
          data-testid="attached-customer-chip"
          className="flex items-center gap-2 rounded-card border border-status-success/40 bg-status-success/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-status-success"
        >
          <span aria-label="Attached customer">
            {customer.name ?? customer.email ?? customer.phone ?? "(unknown)"}
          </span>
          <button
            type="button"
            onClick={detachCustomer}
            aria-label="Detach customer"
            className="rounded-badge border border-surface-border bg-surface px-2 text-ink-muted hover:bg-status-danger/10 hover:text-status-danger"
          >
            ×
          </button>
        </span>
      ) : (
        <button
          type="button"
          onClick={openCustomer}
          disabled={customerActionDisabled}
          aria-label="Attach customer"
          className="rounded-card border border-status-success bg-surface px-4 py-2 font-mono text-xs font-bold uppercase tracking-wider text-status-success hover:bg-status-success/5 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Attach Customer
        </button>
      )}

      <button
        type="button"
        onClick={openLookup}
        disabled={refundDisabled}
        aria-label="Refund a sale"
        className="rounded-card border border-brand-copper bg-surface px-4 py-2 font-mono text-xs font-bold uppercase tracking-wider text-brand-copper hover:bg-brand-copper/5 disabled:cursor-not-allowed disabled:opacity-60"
      >
        Refund
      </button>
    </div>
  );
}
