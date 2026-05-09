import { create } from "zustand";

import type {
  ItemLookupResponse,
  WarehouseAvailability,
} from "../api/items";

export interface CartLine {
  id: string;
  sku: string;
  name: string;
  unit_price_cents: number;
  tax_rate: number;
  is_taxable: boolean;
  warehouse_id: string;
  warehouse_name: string;
  bin_id: string;
  bin_name: string;
  quantity: number;
  availability: WarehouseAvailability[];
}

export interface CartTotals {
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
}

interface CartState {
  lines: CartLine[];
  addItem: (item: ItemLookupResponse) => void;
  removeLine: (id: string) => void;
  setQuantity: (id: string, quantity: number) => void;
  setWarehouseBin: (id: string, warehouse_id: string, bin_id: string) => void;
  clear: () => void;
}

interface DefaultLocation {
  warehouse_id: string;
  warehouse_name: string;
  bin_id: string;
  bin_name: string;
}

function pickDefaultLocation(
  availability: WarehouseAvailability[],
): DefaultLocation | null {
  if (availability.length === 0) return null;
  const wh =
    availability.find((w) => w.qty_available > 0) ?? availability[0];
  if (wh.bins.length === 0) {
    return {
      warehouse_id: wh.warehouse_id,
      warehouse_name: wh.warehouse_name,
      bin_id: "",
      bin_name: "",
    };
  }
  const bin = wh.bins.find((b) => b.qty > 0) ?? wh.bins[0];
  return {
    warehouse_id: wh.warehouse_id,
    warehouse_name: wh.warehouse_name,
    bin_id: bin.bin_id,
    bin_name: bin.bin_name,
  };
}

function newLineId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `line-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export const useCart = create<CartState>((set) => ({
  lines: [],

  addItem: (item) =>
    set((state) => {
      const location = pickDefaultLocation(item.availability);
      const warehouseId = location?.warehouse_id ?? "";
      const binId = location?.bin_id ?? "";

      const existing = state.lines.find(
        (l) =>
          l.sku === item.sku &&
          l.warehouse_id === warehouseId &&
          l.bin_id === binId,
      );

      if (existing) {
        return {
          lines: state.lines.map((l) =>
            l.id === existing.id ? { ...l, quantity: l.quantity + 1 } : l,
          ),
        };
      }

      const newLine: CartLine = {
        id: newLineId(),
        sku: item.sku,
        name: item.name,
        unit_price_cents: item.unit_price_cents,
        tax_rate: item.tax_rate,
        is_taxable: item.is_taxable,
        warehouse_id: warehouseId,
        warehouse_name: location?.warehouse_name ?? "",
        bin_id: binId,
        bin_name: location?.bin_name ?? "",
        quantity: 1,
        availability: item.availability,
      };
      return { lines: [...state.lines, newLine] };
    }),

  removeLine: (id) =>
    set((state) => ({
      lines: state.lines.filter((l) => l.id !== id),
    })),

  setQuantity: (id, quantity) =>
    set((state) => ({
      lines: state.lines.map((l) =>
        l.id === id
          ? { ...l, quantity: Math.max(1, Math.floor(quantity)) }
          : l,
      ),
    })),

  setWarehouseBin: (id, warehouse_id, bin_id) =>
    set((state) => ({
      lines: state.lines.map((l) => {
        if (l.id !== id) return l;
        const wh = l.availability.find(
          (w) => w.warehouse_id === warehouse_id,
        );
        const bin = wh?.bins.find((b) => b.bin_id === bin_id);
        return {
          ...l,
          warehouse_id,
          warehouse_name: wh?.warehouse_name ?? l.warehouse_name,
          bin_id,
          bin_name: bin?.bin_name ?? l.bin_name,
        };
      }),
    })),

  clear: () => set({ lines: [] }),
}));

export function computeTotals(lines: CartLine[]): CartTotals {
  let subtotal = 0;
  let tax = 0;
  for (const line of lines) {
    const lineTotal = line.unit_price_cents * line.quantity;
    subtotal += lineTotal;
    if (line.is_taxable) {
      tax += Math.round(lineTotal * line.tax_rate);
    }
  }
  return {
    subtotal_cents: subtotal,
    tax_cents: tax,
    total_cents: subtotal + tax,
  };
}

export function formatCents(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}$${(abs / 100).toFixed(2)}`;
}
