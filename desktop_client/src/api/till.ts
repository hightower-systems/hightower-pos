import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "./client";

// Canonical denomination keys + display labels. Must stay in lockstep
// with pos_service/services/till.py:DENOMINATIONS -- the backend
// rejects any key not in that allowlist. Order is largest-first so
// the modals render the same top-to-bottom layout as the PDF.
export const DENOMINATIONS: ReadonlyArray<{
  key: string;
  label: string;
  cents: number;
}> = [
  { key: "hundred", label: "$100", cents: 10000 },
  { key: "fifty",   label: "$50",  cents: 5000  },
  { key: "twenty",  label: "$20",  cents: 2000  },
  { key: "ten",     label: "$10",  cents: 1000  },
  { key: "five",    label: "$5",   cents: 500   },
  { key: "one",     label: "$1",   cents: 100   },
  { key: "quarter", label: "25¢",  cents: 25    },
  { key: "dime",    label: "10¢",  cents: 10    },
  { key: "nickel",  label: "5¢",   cents: 5     },
  { key: "penny",   label: "1¢",   cents: 1     },
];

export type DenominationCounts = Record<string, number>;

export function denominationsToCents(counts: DenominationCounts): number {
  return DENOMINATIONS.reduce(
    (total, d) => total + (Math.max(0, Math.trunc(counts[d.key] ?? 0)) * d.cents),
    0,
  );
}

export function formatCents(cents: number): string {
  const negative = cents < 0;
  const abs = Math.abs(cents);
  const dollars = Math.trunc(abs / 100);
  const rem = abs % 100;
  const formatted = `$${dollars.toLocaleString()}.${rem.toString().padStart(2, "0")}`;
  return negative ? `-${formatted}` : formatted;
}

export interface TillSessionBrief {
  session_id: string;
  status: "OPEN" | "CLOSED";
  opened_at: string;
}

export interface CurrentTillNone {
  status: "NONE";
}

export interface CurrentTillOpen {
  status: "OPEN";
  session_id: string;
  opening_float_cents: number;
  cash_sales_cents: number;
  cash_refunds_cents: number;
  transaction_count: number;
  cash_transaction_count: number;
  expected_closing_cents: number;
  opened_at: string;
}

export type CurrentTill = CurrentTillNone | CurrentTillOpen;

export interface OpenTillResponse {
  session_id: string;
  opening_float_cents: number;
  opened_at: string;
}

export interface CloseTillResponse {
  session_id: string;
  status: "CLOSED";
  opening_float_cents: number;
  cash_sales_cents: number;
  cash_refunds_cents: number;
  expected_closing_cents: number;
  closing_count_cents: number;
  variance_cents: number;
  pdf_url: string;
  closed_at: string;
}

export function useCurrentTill(refetchIntervalMs?: number) {
  return useQuery({
    queryKey: ["till", "current"],
    queryFn: () => api<CurrentTill>("/api/till/current"),
    refetchInterval: refetchIntervalMs,
    refetchOnWindowFocus: true,
  });
}

export function useOpenTill() {
  return useMutation({
    mutationFn: (opening_denominations: DenominationCounts) =>
      api<OpenTillResponse>("/api/till/open", {
        method: "POST",
        body: JSON.stringify({ opening_denominations }),
      }),
  });
}

export function useCloseTill() {
  return useMutation({
    mutationFn: (closing_denominations: DenominationCounts) =>
      api<CloseTillResponse>("/api/till/close", {
        method: "POST",
        body: JSON.stringify({ closing_denominations }),
      }),
  });
}
