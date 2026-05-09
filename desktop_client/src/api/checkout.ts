import { useMutation, useQuery } from "@tanstack/react-query";

import type { CheckoutResultPayload } from "../store/checkout";
import { api } from "./client";

export interface CheckoutLineIn {
  sku: string;
  name: string;
  warehouse_id: string;
  bin_id: string;
  quantity: number;
  is_taxable: boolean;
}

export interface StartCheckoutRequest {
  lines: CheckoutLineIn[];
}

export interface StartCheckoutResponse {
  transaction_id: string;
  status: string;
  tax_rate: number;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
}

export function useStartCheckout() {
  return useMutation<StartCheckoutResponse, Error, StartCheckoutRequest>({
    mutationFn: (body) =>
      api<StartCheckoutResponse>("/api/checkout/start", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export interface ChargeCardResponse {
  transaction_id: string;
  status: string;
}

export function useChargeCard() {
  return useMutation<ChargeCardResponse, Error, { transactionId: string }>({
    mutationFn: ({ transactionId }) =>
      api<ChargeCardResponse>(
        `/api/checkout/${transactionId}/charge-card`,
        { method: "POST" },
      ),
  });
}

export interface CheckoutStatusResponse {
  transaction_id: string;
  status: string;
  is_terminal: boolean;
  result: CheckoutResultPayload | null;
}

const POLL_INTERVAL_MS = 500;

export function useCheckoutStatus(
  transactionId: string | null,
  options: { enabled?: boolean } = {},
) {
  return useQuery<CheckoutStatusResponse, Error>({
    queryKey: ["checkout-status", transactionId],
    queryFn: () =>
      api<CheckoutStatusResponse>(
        `/api/checkout/${transactionId}/status`,
      ),
    enabled: (options.enabled ?? true) && transactionId !== null,
    refetchInterval: (query) =>
      query.state.data?.is_terminal ? false : POLL_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });
}

export interface CancelCheckoutResponse {
  transaction_id: string;
  status: string;
}

export function useCancelCheckout() {
  return useMutation<CancelCheckoutResponse, Error, string>({
    mutationFn: (transactionId) =>
      api<CancelCheckoutResponse>(
        `/api/checkout/${transactionId}/cancel`,
        { method: "POST" },
      ),
  });
}
