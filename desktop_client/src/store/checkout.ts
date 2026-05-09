import { create } from "zustand";

export interface CheckoutResultPayload {
  so_id: string | null;
  windcave_txn_ref: string | null;
  card_brand: string | null;
  card_last4: string | null;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  payment_method: string | null;
  receipt_content: string | null;
}

export type CheckoutPhase = "idle" | "in_flight" | "result";

interface CheckoutState {
  phase: CheckoutPhase;
  transactionId: string | null;
  status: string | null;
  result: CheckoutResultPayload | null;
  error: string | null;
  startedAt: (transactionId: string) => void;
  finished: (
    status: string,
    result: CheckoutResultPayload | null,
    error: string | null,
  ) => void;
  failed: (error: string) => void;
  reset: () => void;
}

export const useCheckout = create<CheckoutState>((set) => ({
  phase: "idle",
  transactionId: null,
  status: null,
  result: null,
  error: null,

  startedAt: (transactionId) =>
    set({
      phase: "in_flight",
      transactionId,
      status: "PAYMENT_IN_FLIGHT",
      result: null,
      error: null,
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
      transactionId: null,
      status: "PAYMENT_FAILED",
      result: null,
      error,
    }),

  reset: () =>
    set({
      phase: "idle",
      transactionId: null,
      status: null,
      result: null,
      error: null,
    }),
}));

export function isSuccessStatus(status: string | null): boolean {
  return status === "COMPLETE";
}
