import { useMutation, useQuery } from "@tanstack/react-query";

import type {
  RefundLookup,
  RefundResultPayload,
} from "../store/refund";
import { api } from "./client";

export function useRefundLookup() {
  return useMutation<RefundLookup, Error, { transactionId: string }>({
    mutationFn: ({ transactionId }) =>
      api<RefundLookup>(
        `/api/refunds/lookup?transaction_id=${encodeURIComponent(transactionId)}`,
      ),
  });
}

export interface StartRefundResponse {
  refund_transaction_id: string;
  status: string;
  payment_method: string | null;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
}

export function useStartRefund() {
  return useMutation<StartRefundResponse, Error, { originalTransactionId: string }>({
    mutationFn: ({ originalTransactionId }) =>
      api<StartRefundResponse>("/api/refunds/start", {
        method: "POST",
        body: JSON.stringify({ original_transaction_id: originalTransactionId }),
      }),
  });
}

export interface ChargeCardRefundResponse {
  refund_transaction_id: string;
  status: string;
}

export function useChargeCardRefund() {
  return useMutation<
    ChargeCardRefundResponse,
    Error,
    { refundTransactionId: string }
  >({
    mutationFn: ({ refundTransactionId }) =>
      api<ChargeCardRefundResponse>(
        `/api/refunds/${refundTransactionId}/charge-card`,
        { method: "POST" },
      ),
  });
}

export interface ChargeCashRefundResponse {
  refund_transaction_id: string;
  status: string;
  refund_so_id: string | null;
}

export function useChargeCashRefund() {
  return useMutation<
    ChargeCashRefundResponse,
    Error,
    { refundTransactionId: string }
  >({
    mutationFn: ({ refundTransactionId }) =>
      api<ChargeCashRefundResponse>(
        `/api/refunds/${refundTransactionId}/charge-cash`,
        { method: "POST" },
      ),
  });
}

export interface RefundStatusResponse {
  refund_transaction_id: string;
  status: string;
  is_terminal: boolean;
  result: RefundResultPayload | null;
}

export function fetchRefundStatus(
  refundTransactionId: string,
): Promise<RefundStatusResponse> {
  return api<RefundStatusResponse>(
    `/api/refunds/${refundTransactionId}/status`,
  );
}

const POLL_INTERVAL_MS = 500;

export function useRefundStatus(
  refundTransactionId: string | null,
  options: { enabled?: boolean } = {},
) {
  return useQuery<RefundStatusResponse, Error>({
    queryKey: ["refund-status", refundTransactionId],
    queryFn: () =>
      api<RefundStatusResponse>(
        `/api/refunds/${refundTransactionId}/status`,
      ),
    enabled: (options.enabled ?? true) && refundTransactionId !== null,
    refetchInterval: (query) =>
      query.state.data?.is_terminal ? false : POLL_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });
}

export interface CancelRefundResponse {
  refund_transaction_id: string;
  status: string;
}

export function useCancelRefund() {
  return useMutation<CancelRefundResponse, Error, string>({
    mutationFn: (refundTransactionId) =>
      api<CancelRefundResponse>(
        `/api/refunds/${refundTransactionId}/cancel`,
        { method: "POST" },
      ),
  });
}
