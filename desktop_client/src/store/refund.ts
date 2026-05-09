import { create } from "zustand";

export interface RefundLookup {
  original_transaction_id: string;
  original_sentry_so_id: string | null;
  completed_at: string;
  payment_method: string | null;
  card_brand: string | null;
  card_last4: string | null;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  lines: Array<Record<string, unknown>>;
  refundable: boolean;
}

export interface RefundResultPayload {
  refund_so_id: string | null;
  windcave_txn_ref: string | null;
  card_brand: string | null;
  card_last4: string | null;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  payment_method: string | null;
  receipt_content: string | null;
}

export type RefundPhase =
  | "idle"
  | "lookup"
  | "confirm"
  | "in_flight"
  | "result";

interface RefundState {
  phase: RefundPhase;
  original: RefundLookup | null;
  refundTransactionId: string | null;
  status: string | null;
  result: RefundResultPayload | null;
  error: string | null;
  openLookup: () => void;
  loaded: (original: RefundLookup) => void;
  startedCardRefund: (refundTransactionId: string) => void;
  finished: (
    status: string,
    result: RefundResultPayload | null,
    error: string | null,
  ) => void;
  failed: (error: string) => void;
  reset: () => void;
}

export const useRefund = create<RefundState>((set) => ({
  phase: "idle",
  original: null,
  refundTransactionId: null,
  status: null,
  result: null,
  error: null,

  openLookup: () =>
    set({
      phase: "lookup",
      original: null,
      refundTransactionId: null,
      status: null,
      result: null,
      error: null,
    }),

  loaded: (original) =>
    set({
      phase: "confirm",
      original,
    }),

  startedCardRefund: (refundTransactionId) =>
    set({
      phase: "in_flight",
      refundTransactionId,
      status: "REFUND_PAYMENT_IN_FLIGHT",
    }),

  finished: (status, result, error) =>
    set({
      phase: "result",
      status,
      result,
      error,
    }),

  failed: (error) =>
    set({
      phase: "result",
      status: "REFUND_PAYMENT_FAILED",
      result: null,
      error,
    }),

  reset: () =>
    set({
      phase: "idle",
      original: null,
      refundTransactionId: null,
      status: null,
      result: null,
      error: null,
    }),
}));

export function isSuccessRefund(status: string | null): boolean {
  return status === "COMPLETE";
}
