import { formatCents, useCart } from "../store/cart";
import { isSuccessStatus, useCheckout } from "../store/checkout";
import { Modal } from "./Modal";

const STATUS_LABELS: Record<string, string> = {
  COMPLETE: "Sale complete",
  PAYMENT_FAILED: "Payment failed",
  VALIDATION_FAILED: "Cart validation failed",
  INVENTORY_UPDATE_FAILED: "Inventory update failed",
  CANCELLED: "Payment cancelled",
};

export function PaymentResult() {
  const phase = useCheckout((s) => s.phase);
  const status = useCheckout((s) => s.status);
  const result = useCheckout((s) => s.result);
  const error = useCheckout((s) => s.error);
  const reset = useCheckout((s) => s.reset);
  const clearCart = useCart((s) => s.clear);

  if (phase !== "result") return null;

  const success = isSuccessStatus(status);
  const title = (status && STATUS_LABELS[status]) ?? "Payment result";

  function handleDone() {
    if (success) clearCart();
    reset();
  }

  return (
    <Modal open={true} onClose={handleDone} title={title}>
      {success && result ? (
        <div
          data-testid="payment-success"
          className="flex flex-col gap-3 font-mono text-sm"
        >
          <div className="flex items-baseline justify-between border-b border-surface-border pb-2">
            <span className="uppercase tracking-wider text-ink-muted">
              Total
            </span>
            <span className="text-2xl font-bold text-brand-red">
              {formatCents(result.total_cents)}
            </span>
          </div>
          {result.card_brand && (
            <div className="flex items-baseline justify-between text-ink-muted">
              <span className="text-xs uppercase tracking-wider">Card</span>
              <span>
                {result.card_brand}
                {result.card_last4 ? ` •••• ${result.card_last4}` : ""}
              </span>
            </div>
          )}
          {result.so_id && (
            <div className="flex items-baseline justify-between text-ink-muted">
              <span className="text-xs uppercase tracking-wider">Sentry SO</span>
              <span className="text-xs">{result.so_id}</span>
            </div>
          )}
          <p className="mt-2 text-center text-xs uppercase tracking-wider text-ink-soft">
            Receipt printing wires up in the next phase.
          </p>
        </div>
      ) : (
        <div data-testid="payment-failure" className="flex flex-col gap-2">
          <p className="font-mono text-sm text-status-danger">
            {error ?? `Status: ${status ?? "unknown"}`}
          </p>
          <p className="font-mono text-xs uppercase tracking-wider text-ink-soft">
            The cart is preserved so you can retry.
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={handleDone}
        autoFocus
        className="mt-6 w-full rounded-card bg-brand-red px-4 py-3 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110"
      >
        Done
      </button>
    </Modal>
  );
}
