import { useMutation } from "@tanstack/react-query";

import { api } from "./client";

export interface BinAvailability {
  bin_id: string;
  bin_name: string;
  qty: number;
}

export interface WarehouseAvailability {
  warehouse_id: string;
  warehouse_name: string;
  qty_available: number;
  bins: BinAvailability[];
}

export interface ItemLookupResponse {
  sku: string;
  name: string;
  barcode: string | null;
  unit_price_cents: number;
  tax_rate: number;
  is_taxable: boolean;
  availability: WarehouseAvailability[];
}

export interface ItemLookupArgs {
  barcode?: string;
  sku?: string;
}

export function useItemLookup() {
  return useMutation<ItemLookupResponse, Error, ItemLookupArgs>({
    mutationFn: async ({ barcode, sku }) => {
      const params = new URLSearchParams();
      if (barcode) params.set("barcode", barcode);
      if (sku) params.set("sku", sku);
      return api<ItemLookupResponse>(`/api/items/lookup?${params.toString()}`);
    },
  });
}
