import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import type { ItemLookupResponse } from "../src/api/items";
import { Cart } from "../src/components/Cart";
import { CartTotals } from "../src/components/CartTotals";
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
      bins: [{ bin_id: "BIN-A1", bin_name: "A1", qty: 5 }],
    },
  ],
};

beforeEach(() => useCart.setState({ lines: [] }));
afterEach(() => useCart.setState({ lines: [] }));

describe("<Cart>", () => {
  it("renders the empty state when there are no lines", () => {
    renderWithQuery(<Cart />);
    expect(screen.getByText(/cart is empty/i)).toBeInTheDocument();
  });

  it("renders one CartLine per cart entry with sku, name, warehouse and bin badges", () => {
    useCart.getState().addItem(ROD);
    renderWithQuery(<Cart />);

    expect(screen.getByText("ROD-100")).toBeInTheDocument();
    expect(screen.getByText("Premium Fly Rod")).toBeInTheDocument();
    expect(screen.getByText(/WH Store/i)).toBeInTheDocument();
    expect(screen.getByText(/BIN A1/i)).toBeInTheDocument();
  });

  it("removes a line when the X button is clicked", async () => {
    useCart.getState().addItem(ROD);
    renderWithQuery(<Cart />);

    await userEvent.click(screen.getByRole("button", { name: /remove rod-100/i }));
    expect(useCart.getState().lines).toHaveLength(0);
    expect(screen.getByText(/cart is empty/i)).toBeInTheDocument();
  });

  it("updates the quantity when the qty input changes", () => {
    useCart.getState().addItem(ROD);
    renderWithQuery(<Cart />);

    const qtyInput = screen.getByLabelText(/quantity for rod-100/i) as HTMLInputElement;
    fireEvent.change(qtyInput, { target: { value: "3" } });

    expect(useCart.getState().lines[0].quantity).toBe(3);
  });
});

describe("<CartTotals>", () => {
  it("shows zero totals on an empty cart", () => {
    renderWithQuery(<CartTotals />);
    expect(screen.getByTestId("cart-subtotal")).toHaveTextContent("$0.00");
    expect(screen.getByTestId("cart-tax")).toHaveTextContent("$0.00");
    expect(screen.getByTestId("cart-total")).toHaveTextContent("$0.00");
  });

  it("computes subtotal, tax (taxable rows only), and total in dollars", () => {
    useCart.getState().addItem(ROD);
    useCart.getState().setQuantity(useCart.getState().lines[0].id, 2);
    renderWithQuery(<CartTotals />);

    const subtotalCents = 19999 * 2;
    const taxCents = Math.round(subtotalCents * 0.081);
    const totalCents = subtotalCents + taxCents;

    expect(screen.getByTestId("cart-subtotal")).toHaveTextContent(
      `$${(subtotalCents / 100).toFixed(2)}`,
    );
    expect(screen.getByTestId("cart-tax")).toHaveTextContent(
      `$${(taxCents / 100).toFixed(2)}`,
    );
    expect(screen.getByTestId("cart-total")).toHaveTextContent(
      `$${(totalCents / 100).toFixed(2)}`,
    );
  });
});
