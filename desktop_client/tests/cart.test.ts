import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { ItemLookupResponse } from "../src/api/items";
import { computeTotals, formatCents, useCart } from "../src/store/cart";

const SAMPLE_ROD: ItemLookupResponse = {
  sku: "ROD-100",
  name: "Premium Fly Rod",
  barcode: "1234567890",
  unit_price_cents: 19999,
  tax_rate: 0.0810,
  is_taxable: true,
  availability: [
    {
      warehouse_id: "WH-STORE",
      warehouse_name: "Store",
      qty_available: 5,
      bins: [
        { bin_id: "BIN-A1", bin_name: "A1", qty: 3 },
        { bin_id: "BIN-A2", bin_name: "A2", qty: 2 },
      ],
    },
    {
      warehouse_id: "WH-AFC",
      warehouse_name: "AFC",
      qty_available: 0,
      bins: [{ bin_id: "BIN-B1", bin_name: "B1", qty: 0 }],
    },
  ],
};

const NON_TAXABLE_LINE: ItemLookupResponse = {
  sku: "GIFT-CARD",
  name: "Gift Card",
  barcode: null,
  unit_price_cents: 5000,
  tax_rate: 0.0810,
  is_taxable: false,
  availability: [
    {
      warehouse_id: "WH-STORE",
      warehouse_name: "Store",
      qty_available: 100,
      bins: [{ bin_id: "BIN-G1", bin_name: "G1", qty: 100 }],
    },
  ],
};

beforeEach(() => {
  useCart.setState({ lines: [] });
});

afterEach(() => {
  useCart.setState({ lines: [] });
});

describe("cart store", () => {
  it("addItem on an empty cart picks the first warehouse with stock", () => {
    useCart.getState().addItem(SAMPLE_ROD);
    const lines = useCart.getState().lines;
    expect(lines).toHaveLength(1);
    expect(lines[0].sku).toBe("ROD-100");
    expect(lines[0].warehouse_id).toBe("WH-STORE");
    expect(lines[0].bin_id).toBe("BIN-A1");
    expect(lines[0].quantity).toBe(1);
  });

  it("addItem twice for the same SKU at the same location increments quantity", () => {
    useCart.getState().addItem(SAMPLE_ROD);
    useCart.getState().addItem(SAMPLE_ROD);
    const lines = useCart.getState().lines;
    expect(lines).toHaveLength(1);
    expect(lines[0].quantity).toBe(2);
  });

  it("addItem assigns unique line ids per add when locations differ", () => {
    useCart.getState().addItem(SAMPLE_ROD);
    useCart.getState().addItem(NON_TAXABLE_LINE);
    const lines = useCart.getState().lines;
    expect(lines).toHaveLength(2);
    expect(new Set(lines.map((l) => l.id)).size).toBe(2);
  });

  it("addItem with all-zero stock still picks the first warehouse and bin", () => {
    const allZero: ItemLookupResponse = {
      ...SAMPLE_ROD,
      availability: [
        {
          warehouse_id: "WH-AFC",
          warehouse_name: "AFC",
          qty_available: 0,
          bins: [{ bin_id: "BIN-B1", bin_name: "B1", qty: 0 }],
        },
      ],
    };
    useCart.getState().addItem(allZero);
    const lines = useCart.getState().lines;
    expect(lines[0].warehouse_id).toBe("WH-AFC");
    expect(lines[0].bin_id).toBe("BIN-B1");
  });

  it("removeLine removes only the targeted line", () => {
    useCart.getState().addItem(SAMPLE_ROD);
    useCart.getState().addItem(NON_TAXABLE_LINE);
    const ids = useCart.getState().lines.map((l) => l.id);
    useCart.getState().removeLine(ids[0]);
    expect(useCart.getState().lines).toHaveLength(1);
    expect(useCart.getState().lines[0].id).toBe(ids[1]);
  });

  it("setQuantity updates the line and clamps to >= 1", () => {
    useCart.getState().addItem(SAMPLE_ROD);
    const id = useCart.getState().lines[0].id;
    useCart.getState().setQuantity(id, 5);
    expect(useCart.getState().lines[0].quantity).toBe(5);
    useCart.getState().setQuantity(id, 0);
    expect(useCart.getState().lines[0].quantity).toBe(1);
    useCart.getState().setQuantity(id, -3);
    expect(useCart.getState().lines[0].quantity).toBe(1);
  });

  it("setWarehouseBin updates names along with ids when moving to a known location", () => {
    useCart.getState().addItem(SAMPLE_ROD);
    const id = useCart.getState().lines[0].id;
    useCart.getState().setWarehouseBin(id, "WH-AFC", "BIN-B1");
    const line = useCart.getState().lines[0];
    expect(line.warehouse_id).toBe("WH-AFC");
    expect(line.warehouse_name).toBe("AFC");
    expect(line.bin_id).toBe("BIN-B1");
    expect(line.bin_name).toBe("B1");
  });

  it("clear empties the cart", () => {
    useCart.getState().addItem(SAMPLE_ROD);
    useCart.getState().addItem(NON_TAXABLE_LINE);
    useCart.getState().clear();
    expect(useCart.getState().lines).toEqual([]);
  });
});

describe("computeTotals", () => {
  it("returns zeros for an empty cart", () => {
    expect(computeTotals([])).toEqual({
      subtotal_cents: 0,
      tax_cents: 0,
      total_cents: 0,
    });
  });

  it("taxes only taxable lines and rounds tax per line", () => {
    useCart.getState().addItem(SAMPLE_ROD);
    useCart.getState().addItem(NON_TAXABLE_LINE);
    useCart.getState().setQuantity(useCart.getState().lines[0].id, 2);
    const totals = computeTotals(useCart.getState().lines);

    expect(totals.subtotal_cents).toBe(19999 * 2 + 5000);
    expect(totals.tax_cents).toBe(Math.round(19999 * 2 * 0.081));
    expect(totals.total_cents).toBe(totals.subtotal_cents + totals.tax_cents);
  });
});

describe("formatCents", () => {
  it("formats positive values with two decimals and a dollar sign", () => {
    expect(formatCents(0)).toBe("$0.00");
    expect(formatCents(150)).toBe("$1.50");
    expect(formatCents(19999)).toBe("$199.99");
  });

  it("formats negative values with a leading minus", () => {
    expect(formatCents(-500)).toBe("-$5.00");
  });
});
