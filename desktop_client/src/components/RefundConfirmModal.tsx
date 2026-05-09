import {
  fetchRefundStatus,
  useChargeCardRefund,
  useChargeCashRefund,
  useStartRefund,
} from "../api/refunds";
import { formatCents } from "../store/cart";
import { useRefund } from "../store/refund";
import { Modal } from "./Modal";

export function RefundConfirmModal() {
  const phase = useRefund((s) => s.phase);
  const original = useRefund((s) => s.original);
  const startedCardRefund = useRefund((s) => s.startedCardRefund);
  const finished = useRefund((s) => s.finished);
  const failed = useRefund((s) => s.failed);
  const reset = useRefund((s) => s.reset);
  const start = useStartRefund();
  const chargeCard = useChargeCardRefund();
  const chargeCash = useChargeCashRefund();

  const isOpen = phase === "confirm" && original !== null;
  const isPending = start.isPending || chargeCard.isPending || chargeCash.isPending;

  async function handleConfirm() {
    if (!original) return;
    try {
      const startResp = await start.mutateAsync({
        originalTransactionId: original.original_transaction_id,
      });
      if (startResp.payment_method === "card") {
        const chargeResp = await chargeCard.mutateAsync({
          refundTransactionId: startResp.refund_transaction_id,
        });
        startedCardRefund(chargeResp.refund_transaction_id);
      } else {
        await chargeCash.mutateAsync({
          refundTransactionId: startResp.refund_transaction_id,
        });
        try {
          const status = await fetchRefundStatus(
            startResp.refund_transaction_id,
          );
          finished(status.status, status.result, null);
        } catch {
          finished(
            "COMPLETE",
            {
              refund_so_id: null,
              windcave_txn_ref: null,
              card_brand: null,
              card_last4: null,
              subtotal_cents: startResp.subtotal_cents,
              tax_cents: startResp.tax_cents,
              total_cents: startResp.total_cents,
              payment_method: "cash",
              receipt_content: null,
            },
            "Receipt unavailable; refund recorded.",
          );
        }
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not process refund.";
      failed(message);
    }
  }

  if (!isOpen || !original) return null;

  const tenderLabel =
    original.payment_method === "card"
      ? `Card ${original.card_brand ?? ""} ${original.card_last4 ? `•••• ${original.card_last4}` : ""}`.trim()
      : original.payment_method === "cash"
        ? "Cash"
        : original.payment_method ?? "unknown";

  return (
    <Modal open={true} onClose={reset} title="Refund: confirm">
      <div className="flex flex-col gap-3">
        <div className="rounded-card border border-surface-border bg-surface-card p-4">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-soft">
            Original transaction
          </p>
          <p className="font-mono text-xs text-ink-muted">
            {original.original_transaction_id}
          </p>
          {original.original_sentry_so_id && (
            <p className="font-mono text-xs text-ink-muted">
              SO {original.original_sentry_so_id}
            </p>
          )}
          <div className="mt-3 flex items-baseline justify-between">
            <span className="font-mono text-xs uppercase tracking-wider text-ink-muted">
              Tender (locked)
            </span>
            <span className="font-mono text-sm font-bold uppercase tracking-wider text-brand-copper">
              {tenderLabel}
            </span>
          </div>
          <div className="mt-2 flex items-baseline justify-between border-t border-surface-border pt-2">
            <span className="font-mono text-xs uppercase tracking-wider text-ink-muted">
              Refund total
            </span>
            <span className="font-mono text-2xl font-bold text-brand-red">
              {formatCents(original.total_cents)}
            </span>
          </div>
          <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-ink-soft">
            {original.lines.length} line
            {original.lines.length === 1 ? "" : "s"} · full-order refund
          </p>
        </div>

        {(start.isError || chargeCard.isError || chargeCash.isError) && (
          <p
            role="alert"
            className="rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-status-danger"
          >
            {start.error?.message ??
              chargeCard.error?.message ??
              chargeCash.error?.message ??
              "Could not process refund."}
          </p>
        )}

        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={reset}
            disabled={isPending}
            className="flex-1 rounded-card border border-surface-border bg-surface px-4 py-3 font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted hover:bg-surface-card disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={isPending}
            className="flex-1 rounded-card bg-brand-red px-4 py-3 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isPending ? "Refunding..." : "Refund"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
