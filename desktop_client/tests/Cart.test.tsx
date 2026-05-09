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

const ROD_TWO_WAREHOUSES: ItemLookupResponse = {
  ...ROD,
  availability: [
    ROD.availability[0],
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

  it("opens the WarehousePicker when the warehouse badge is clicked", async () => {
    useCart.getState().addItem(ROD);
    renderWithQuery(<Cart />);

    await userEvent.click(
      screen.getByRole("button", { name: /change warehouse for rod-100/i }),
    );

    expect(
      screen.getByRole("dialog", { name: /warehouse for rod-100/i }),
    ).toBeInTheDocument();
  });

  it("opens the BinPicker when the bin badge is clicked", async () => {
    useCart.getState().addItem(ROD);
    renderWithQuery(<Cart />);

    await userEvent.click(
      screen.getByRole("button", { name: /change bin for rod-100/i }),
    );

    expect(
      screen.getByRole("dialog", { name: /bin in store/i }),
    ).toBeInTheDocument();
  });

  it("renders an oversold warning when qty exceeds the selected bin's stock", () => {
    useCart.getState().addItem(ROD);
    const id = useCart.getState().lines[0].id;
    useCart.getState().setQuantity(id, 99);
    renderWithQuery(<Cart />);

    expect(screen.getByTestId("oversold-warning")).toHaveTextContent(
      /only 5 in bin/i,
    );
  });

  it("renders 'Out of stock here' when the selected bin has zero stock", () => {
    const ZERO: typeof ROD = {
      ...ROD,
      availability: [
        {
          warehouse_id: "WH-STORE",
          warehouse_name: "Store",
          qty_available: 0,
          bins: [{ bin_id: "BIN-EMPTY", bin_name: "EMPTY", qty: 0 }],
        },
      ],
    };
    useCart.getState().addItem(ZERO);
    renderWithQuery(<Cart />);

    expect(screen.getByTestId("oversold-warning")).toHaveTextContent(
      /out of stock here/i,
    );
  });

  it("does not render the oversold warning when qty is within bin stock", () => {
    useCart.getState().addItem(ROD);
    renderWithQuery(<Cart />);
    expect(screen.queryByTestId("oversold-warning")).not.toBeInTheDocument();
  });

  it("hides the Split badge when only one warehouse is on file", () => {
    useCart.getState().addItem(ROD);
    renderWithQuery(<Cart />);
    expect(
      screen.queryByRole("button", { name: /split rod-100/i }),
    ).not.toBeInTheDocument();
  });

  it("shows the Split badge when multiple warehouses exist and opens the modal on click", async () => {
    useCart.getState().addItem(ROD_TWO_WAREHOUSES);
    renderWithQuery(<Cart />);

    await userEvent.click(
      screen.getByRole("button", { name: /split rod-100/i }),
    );
    expect(
      screen.getByRole("dialog", { name: /split rod-100/i }),
    ).toBeInTheDocument();
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
