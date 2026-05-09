import { useEffect, useRef } from "react";

import { usePrintReceipt } from "../api/printAgent";
import { formatCents } from "../store/cart";
import { isSuccessRefund, useRefund } from "../store/refund";
import { Modal } from "./Modal";

const STATUS_LABELS: Record<string, string> = {
  COMPLETE: "Refund complete",
  REFUND_PAYMENT_FAILED: "Refund failed",
  REFUND_INVENTORY_UPDATE_FAILED: "Refund inventory update failed",
  CANCELLED: "Refund cancelled",
};

export function RefundResult() {
  const phase = useRefund((s) => s.phase);
  const status = useRefund((s) => s.status);
  const result = useRefund((s) => s.result);
  const refundTransactionId = useRefund((s) => s.refundTransactionId);
  const error = useRefund((s) => s.error);
  const reset = useRefund((s) => s.reset);
  const printReceipt = usePrintReceipt();
  const printedRef = useRef<string | null>(null);

  const success = isSuccessRefund(status);
  const isResult = phase === "result";

  useEffect(() => {
    if (!isResult || !success || !result?.receipt_content) return;
    const key = refundTransactionId ?? result.refund_so_id ?? "anon";
    if (printedRef.current === key) return;
    printedRef.current = key;
    printReceipt.mutate({
      content: result.receipt_content,
      open_drawer_after: result.payment_method === "cash",
    });
  }, [isResult, success, result, refundTransactionId, printReceipt]);

  useEffect(() => {
    if (!isResult) printedRef.current = null;
  }, [isResult]);

  if (!isResult) return null;

  const title = (status && STATUS_LABELS[status]) ?? "Refund result";

  return (
    <Modal open={true} onClose={reset} title={title}>
      {success && result ? (
        <div
          data-testid="refund-success"
          className="flex flex-col gap-3 font-mono text-sm"
        >
          <div className="flex items-baseline justify-between border-b border-surface-border pb-2">
            <span className="uppercase tracking-wider text-ink-muted">
              Refunded
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
          {result.refund_so_id && (
            <div className="flex items-baseline justify-between text-ink-muted">
              <span className="text-xs uppercase tracking-wider">
                Refund SO
              </span>
              <span className="text-xs">{result.refund_so_id}</span>
            </div>
          )}
          <p
            data-testid="refund-receipt-status"
            className={`mt-2 text-center text-xs uppercase tracking-wider ${printReceipt.isError ? "text-status-warning" : "text-ink-soft"}`}
          >
            {printReceipt.isError
              ? "Receipt did not print -- reprint manually."
              : printReceipt.isPending
                ? "Printing receipt..."
                : printReceipt.isSuccess
                  ? "Receipt printed."
                  : result.receipt_content
                    ? "Sending receipt to printer..."
                    : "Receipt unavailable."}
          </p>
        </div>
      ) : (
        <div data-testid="refund-failure" className="flex flex-col gap-2">
          <p className="font-mono text-sm text-status-danger">
            {error ?? `Status: ${status ?? "unknown"}`}
          </p>
          <p className="font-mono text-xs uppercase tracking-wider text-ink-soft">
            No money moved. The original sale is unchanged.
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={reset}
        autoFocus
        className="mt-6 w-full rounded-card bg-brand-red px-4 py-3 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110"
      >
        Done
      </button>
    </Modal>
  );
}
