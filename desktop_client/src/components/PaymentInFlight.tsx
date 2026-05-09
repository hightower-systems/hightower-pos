import { useEffect } from "react";

import { useCancelCheckout, useCheckoutStatus } from "../api/checkout";
import { useCheckout } from "../store/checkout";
import { Modal } from "./Modal";

export function PaymentInFlight() {
  const phase = useCheckout((s) => s.phase);
  const transactionId = useCheckout((s) => s.transactionId);
  const finished = useCheckout((s) => s.finished);
  const cancel = useCancelCheckout();

  const isOpen = phase === "in_flight" && transactionId !== null;
  const status = useCheckoutStatus(transactionId, { enabled: isOpen });

  useEffect(() => {
    const data = status.data;
    if (!data) return;
    if (data.is_terminal) {
      finished(data.status, data.result, null);
    }
  }, [status.data, finished]);

  function handleCancel() {
    if (!transactionId) return;
    cancel.mutate(transactionId);
  }

  if (!isOpen) return null;

  const currentStatus = status.data?.status ?? "PAYMENT_IN_FLIGHT";

  return (
    <Modal open={true} onClose={handleCancel} title="Card payment">
      <div className="flex flex-col items-center gap-4 py-4 text-center">
        <div
          aria-label="payment-spinner"
          className="h-12 w-12 animate-spin rounded-full border-4 border-surface-border border-t-brand-red"
        />
        <p className="font-mono text-sm font-bold uppercase tracking-wider text-ink">
          Tap, insert, or swipe the card
        </p>
        <p className="font-mono text-xs uppercase tracking-wider text-ink-muted">
          on the terminal
        </p>
        <p
          data-testid="checkout-status"
          className="font-mono text-[10px] uppercase tracking-wider text-ink-soft"
        >
          {currentStatus}
        </p>
      </div>
      <button
        type="button"
        onClick={handleCancel}
        disabled={cancel.isPending}
        className="mt-2 w-full rounded-card border border-surface-border bg-surface px-4 py-2 font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted hover:bg-status-danger/10 hover:text-status-danger disabled:opacity-60"
      >
        {cancel.isPending ? "Cancelling..." : "Cancel"}
      </button>
    </Modal>
  );
}
