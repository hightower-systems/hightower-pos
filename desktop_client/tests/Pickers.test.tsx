import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import type { ItemLookupResponse } from "../src/api/items";
import { BinPicker } from "../src/components/BinPicker";
import { WarehousePicker } from "../src/components/WarehousePicker";
import { useCart } from "../src/store/cart";
import { renderWithQuery } from "./utils";

const ROD: ItemLookupResponse = {
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
      qty_available: 7,
      bins: [{ bin_id: "BIN-B1", bin_name: "B1", qty: 7 }],
    },
  ],
};

beforeEach(() => useCart.setState({ lines: [] }));
afterEach(() => useCart.setState({ lines: [] }));

function seedLine() {
  useCart.getState().addItem(ROD);
  return useCart.getState().lines[0];
}

describe("<WarehousePicker>", () => {
  it("lists every warehouse on the line with its name and qty_available", () => {
    const line = seedLine();
    renderWithQuery(
      <WarehousePicker open={true} onClose={() => {}} line={line} />,
    );

    expect(screen.getByText("Store")).toBeInTheDocument();
    expect(screen.getByText("AFC")).toBeInTheDocument();
    expect(screen.getByRole("button", { pressed: true })).toHaveTextContent(
      "Store",
    );
  });

  it("switches the line warehouse and auto-picks a default bin on click", async () => {
    const line = seedLine();
    const onClose = vi.fn();
    renderWithQuery(
      <WarehousePicker open={true} onClose={onClose} line={line} />,
    );

    const afcButton = screen.getByRole("button", { pressed: false });
    await userEvent.click(afcButton);

    const after = useCart.getState().lines[0];
    expect(after.warehouse_id).toBe("WH-AFC");
    expect(after.warehouse_name).toBe("AFC");
    expect(after.bin_id).toBe("BIN-B1");
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("<BinPicker>", () => {
  it("lists only the bins for the line's currently-selected warehouse", () => {
    const line = seedLine();
    renderWithQuery(
      <BinPicker open={true} onClose={() => {}} line={line} />,
    );

    expect(screen.getByText(/BIN A1/i)).toBeInTheDocument();
    expect(screen.getByText(/BIN A2/i)).toBeInTheDocument();
    expect(screen.queryByText(/BIN B1/i)).not.toBeInTheDocument();
  });

  it("switches only the bin and leaves the warehouse alone on click", async () => {
    const line = seedLine();
    const onClose = vi.fn();
    renderWithQuery(<BinPicker open={true} onClose={onClose} line={line} />);

    await userEvent.click(screen.getByRole("button", { name: /BIN A2/i }));

    const after = useCart.getState().lines[0];
    expect(after.warehouse_id).toBe("WH-STORE");
    expect(after.bin_id).toBe("BIN-A2");
    expect(after.bin_name).toBe("A2");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("renders a friendly empty-state message when the warehouse has no bins", () => {
    const line = {
      ...seedLine(),
      availability: [
        {
          warehouse_id: "WH-STORE",
          warehouse_name: "Store",
          qty_available: 0,
          bins: [],
        },
      ],
    };
    renderWithQuery(<BinPicker open={true} onClose={() => {}} line={line} />);
    expect(screen.getByText(/no bins on file/i)).toBeInTheDocument();
  });
});
