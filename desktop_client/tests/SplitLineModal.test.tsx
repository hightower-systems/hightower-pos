import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import type { ItemLookupResponse } from "../src/api/items";
import { SplitLineModal } from "../src/components/SplitLineModal";
import { useCart } from "../src/store/cart";
import { renderWithQuery } from "./utils";

const ROD_TWO_WAREHOUSES: ItemLookupResponse = {
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
      bins: [{ bin_id: "BIN-A1", bin_name: "A1", qty: 5 }],
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

function seedLineWithQuantity(qty: number) {
  useCart.getState().addItem(ROD_TWO_WAREHOUSES);
  const id = useCart.getState().lines[0].id;
  useCart.getState().setQuantity(id, qty);
  return useCart.getState().lines[0];
}

describe("<SplitLineModal>", () => {
  it("renders one row per warehouse with the line's qty pre-loaded into the original location", () => {
    const line = seedLineWithQuantity(5);
    renderWithQuery(
      <SplitLineModal open={true} onClose={() => {}} line={line} />,
    );

    const storeQty = screen.getByLabelText(/quantity from store/i) as HTMLInputElement;
    const afcQty = screen.getByLabelText(/quantity from afc/i) as HTMLInputElement;
    expect(storeQty.value).toBe("5");
    expect(afcQty.value).toBe("0");
    expect(screen.getByTestId("split-total")).toHaveTextContent("5 / 5");
  });

  it("disables Save until total equals the target qty", async () => {
    const line = seedLineWithQuantity(5);
    renderWithQuery(
      <SplitLineModal open={true} onClose={() => {}} line={line} />,
    );

    const storeQty = screen.getByLabelText(/quantity from store/i);
    fireEvent.change(storeQty, { target: { value: "3" } });
    expect(screen.getByRole("button", { name: /save split/i })).toBeDisabled();
    expect(screen.getByTestId("split-total")).toHaveTextContent("3 / 5");

    const afcQty = screen.getByLabelText(/quantity from afc/i);
    fireEvent.change(afcQty, { target: { value: "2" } });
    expect(screen.getByRole("button", { name: /save split/i })).toBeEnabled();
    expect(screen.getByTestId("split-total")).toHaveTextContent("5 / 5");
  });

  it("commits the split to the store and closes when Save is clicked", async () => {
    const line = seedLineWithQuantity(5);
    const onClose = vi.fn();
    renderWithQuery(
      <SplitLineModal open={true} onClose={onClose} line={line} />,
    );

    fireEvent.change(screen.getByLabelText(/quantity from store/i), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText(/quantity from afc/i), {
      target: { value: "2" },
    });
    await userEvent.click(screen.getByRole("button", { name: /save split/i }));

    const lines = useCart.getState().lines;
    expect(lines).toHaveLength(2);
    expect(
      lines.find((l) => l.warehouse_id === "WH-STORE")!.quantity,
    ).toBe(3);
    expect(
      lines.find((l) => l.warehouse_id === "WH-AFC")!.quantity,
    ).toBe(2);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("Cancel closes without changing the cart", async () => {
    const line = seedLineWithQuantity(5);
    const before = useCart.getState().lines;
    const onClose = vi.fn();
    renderWithQuery(
      <SplitLineModal open={true} onClose={onClose} line={line} />,
    );

    fireEvent.change(screen.getByLabelText(/quantity from store/i), {
      target: { value: "3" },
    });
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(useCart.getState().lines).toEqual(before);
    expect(onClose).toHaveBeenCalledOnce();
  });
});
