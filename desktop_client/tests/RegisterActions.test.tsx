import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { RegisterActions } from "../src/components/RegisterActions";
import { useCheckout } from "../src/store/checkout";
import { useCustomer } from "../src/store/customer";
import { useRefund } from "../src/store/refund";
import { renderWithQuery } from "./utils";

beforeEach(() => {
  useRefund.getState().reset();
  useCheckout.getState().reset();
  useCustomer.getState().reset();
});

afterEach(() => {
  useRefund.getState().reset();
  useCheckout.getState().reset();
  useCustomer.getState().reset();
});

describe("<RegisterActions>", () => {
  it("renders an enabled Refund button when both stores are idle", () => {
    renderWithQuery(<RegisterActions />);
    expect(
      screen.getByRole("button", { name: /refund a sale/i }),
    ).toBeEnabled();
  });

  it("opens the refund lookup phase on click", async () => {
    renderWithQuery(<RegisterActions />);
    await userEvent.click(screen.getByRole("button", { name: /refund a sale/i }));
    expect(useRefund.getState().phase).toBe("lookup");
  });

  it("disables Refund while a checkout is mid-flight", () => {
    useCheckout.getState().startedAt("txn-1");
    renderWithQuery(<RegisterActions />);
    expect(
      screen.getByRole("button", { name: /refund a sale/i }),
    ).toBeDisabled();
  });

  it("disables Refund while another refund is mid-flight", () => {
    useRefund.getState().openLookup();
    renderWithQuery(<RegisterActions />);
    expect(
      screen.getByRole("button", { name: /refund a sale/i }),
    ).toBeDisabled();
  });

  it("Attach Customer opens the customer lookup phase", async () => {
    renderWithQuery(<RegisterActions />);
    await userEvent.click(
      screen.getByRole("button", { name: /attach customer/i }),
    );
    expect(useCustomer.getState().phase).toBe("lookup");
  });

  it("F3 opens the refund lookup phase", () => {
    renderWithQuery(<RegisterActions />);
    fireEvent.keyDown(document, { key: "F3" });
    expect(useRefund.getState().phase).toBe("lookup");
  });

  it("F4 opens the customer lookup phase when no customer attached", () => {
    renderWithQuery(<RegisterActions />);
    fireEvent.keyDown(document, { key: "F4" });
    expect(useCustomer.getState().phase).toBe("lookup");
  });

  it("F4 is a no-op when a customer is already attached", () => {
    useCustomer.getState().setAttached({
      customer_id: "cust-1",
      name: "Pat Smith",
      email: null,
      phone: null,
      registered: true,
    });
    renderWithQuery(<RegisterActions />);
    fireEvent.keyDown(document, { key: "F4" });
    expect(useCustomer.getState().phase).toBe("idle");
  });

  it("F3 is a no-op while a checkout is mid-flight", () => {
    useCheckout.getState().startedAt("txn-1");
    renderWithQuery(<RegisterActions />);
    fireEvent.keyDown(document, { key: "F3" });
    expect(useRefund.getState().phase).toBe("idle");
  });

  it("renders the F3 and F4 keyboard hints on the buttons", () => {
    renderWithQuery(<RegisterActions />);
    expect(
      screen.getByRole("button", { name: /refund a sale/i }),
    ).toHaveTextContent(/F3/);
    expect(
      screen.getByRole("button", { name: /attach customer/i }),
    ).toHaveTextContent(/F4/);
  });

  it("renders the chip with the attached customer's name and detaches on click", async () => {
    useCustomer.getState().setAttached({
      customer_id: "cust-1",
      name: "Pat Smith",
      email: "pat@example.com",
      phone: null,
      registered: true,
    });
    renderWithQuery(<RegisterActions />);
    expect(screen.getByTestId("attached-customer-chip")).toHaveTextContent(
      "Pat Smith",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /detach customer/i }),
    );
    expect(useCustomer.getState().attached).toBeNull();
  });
});
