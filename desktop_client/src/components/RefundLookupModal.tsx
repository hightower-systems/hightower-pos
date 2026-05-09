import { type FormEvent, useState } from "react";

import { useRefundLookup } from "../api/refunds";
import { formatCents } from "../store/cart";
import { useRefund } from "../store/refund";
import { Modal } from "./Modal";

export function RefundLookupModal() {
  const phase = useRefund((s) => s.phase);
  const loaded = useRefund((s) => s.loaded);
  const reset = useRefund((s) => s.reset);
  const lookup = useRefundLookup();
  const [txnId, setTxnId] = useState("");

  const isOpen = phase === "lookup";

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const id = txnId.trim();
    if (!id) return;
    lookup.mutate(
      { transactionId: id },
      {
        onSuccess: (data) => {
          if (data.refundable) {
            loaded(data);
            setTxnId("");
          }
        },
      },
    );
  }

  function handleCancel() {
    setTxnId("");
    reset();
  }

  if (!isOpen) return null;

  return (
    <Modal open={true} onClose={handleCancel} title="Refund: find sale">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="block">
          <span className="mb-1 block font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted">
            Original transaction id
          </span>
          <input
            type="text"
            value={txnId}
            onChange={(event) => setTxnId(event.target.value)}
            placeholder="txn-..."
            autoFocus
            aria-label="Original transaction id"
            className="w-full rounded-card border border-surface-inputBorder bg-surface-input px-3 py-2 font-mono text-base text-ink outline-none focus:border-brand-red"
          />
        </label>

        {lookup.isError && (
          <p
            role="alert"
            className="rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-status-danger"
          >
            {lookup.error?.message ?? "Could not find that transaction."}
          </p>
        )}

        {lookup.data && lookup.data.refundable === false && (
          <p
            role="status"
            className="rounded-card border border-status-warning/40 bg-status-warning/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-status-warning"
          >
            Not refundable. {lookup.data.payment_method ?? "unknown tender"} ·{" "}
            {formatCents(lookup.data.total_cents)}
          </p>
        )}

        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={handleCancel}
            className="flex-1 rounded-card border border-surface-border bg-surface px-4 py-2 font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted hover:bg-surface-card"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!txnId.trim() || lookup.isPending}
            className="flex-1 rounded-card bg-brand-red px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {lookup.isPending ? "Looking up..." : "Look up"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
