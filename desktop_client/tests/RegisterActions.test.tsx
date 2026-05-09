import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { RegisterActions } from "../src/components/RegisterActions";
import { useCheckout } from "../src/store/checkout";
import { useRefund } from "../src/store/refund";
import { renderWithQuery } from "./utils";

beforeEach(() => {
  useRefund.getState().reset();
  useCheckout.getState().reset();
});

afterEach(() => {
  useRefund.getState().reset();
  useCheckout.getState().reset();
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
});
