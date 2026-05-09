import { useCheckout } from "../store/checkout";
import { useRefund } from "../store/refund";

export function RegisterActions() {
  const openLookup = useRefund((s) => s.openLookup);
  const refundPhase = useRefund((s) => s.phase);
  const checkoutPhase = useCheckout((s) => s.phase);

  const disabled = refundPhase !== "idle" || checkoutPhase !== "idle";

  return (
    <div className="flex justify-end">
      <button
        type="button"
        onClick={openLookup}
        disabled={disabled}
        aria-label="Refund a sale"
        className="rounded-card border border-brand-copper bg-surface px-4 py-2 font-mono text-xs font-bold uppercase tracking-wider text-brand-copper hover:bg-brand-copper/5 disabled:cursor-not-allowed disabled:opacity-60"
      >
        Refund
      </button>
    </div>
  );
}
