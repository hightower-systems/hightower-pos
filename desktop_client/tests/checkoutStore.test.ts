import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { isSuccessStatus, useCheckout } from "../src/store/checkout";

const SAMPLE_RESULT = {
  so_id: "SO-1",
  windcave_txn_ref: "WC-1",
  card_brand: "VISA",
  card_last4: "4242",
  subtotal_cents: 19999,
  tax_cents: 1620,
  total_cents: 21619,
  payment_method: "card",
  receipt_content: "(receipt body)",
};

beforeEach(() => useCheckout.getState().reset());
afterEach(() => useCheckout.getState().reset());

describe("checkout store", () => {
  it("starts in the idle phase", () => {
    expect(useCheckout.getState().phase).toBe("idle");
    expect(useCheckout.getState().transactionId).toBeNull();
  });

  it("startedAt transitions idle -> in_flight and pins the transaction id", () => {
    useCheckout.getState().startedAt("txn-123");
    expect(useCheckout.getState().phase).toBe("in_flight");
    expect(useCheckout.getState().transactionId).toBe("txn-123");
    expect(useCheckout.getState().status).toBe("PAYMENT_IN_FLIGHT");
  });

  it("finished transitions in_flight -> result with the supplied status and result", () => {
    useCheckout.getState().startedAt("txn-123");
    useCheckout.getState().finished("COMPLETE", SAMPLE_RESULT, null);
    expect(useCheckout.getState().phase).toBe("result");
    expect(useCheckout.getState().status).toBe("COMPLETE");
    expect(useCheckout.getState().result).toEqual(SAMPLE_RESULT);
    expect(useCheckout.getState().error).toBeNull();
  });

  it("failed jumps from any phase straight to result with PAYMENT_FAILED", () => {
    useCheckout.getState().failed("network blew up");
    expect(useCheckout.getState().phase).toBe("result");
    expect(useCheckout.getState().status).toBe("PAYMENT_FAILED");
    expect(useCheckout.getState().error).toBe("network blew up");
    expect(useCheckout.getState().result).toBeNull();
  });

  it("reset clears every field back to idle", () => {
    useCheckout.getState().startedAt("txn-123");
    useCheckout.getState().finished("COMPLETE", SAMPLE_RESULT, null);
    useCheckout.getState().reset();
    const state = useCheckout.getState();
    expect(state.phase).toBe("idle");
    expect(state.transactionId).toBeNull();
    expect(state.status).toBeNull();
    expect(state.result).toBeNull();
    expect(state.error).toBeNull();
  });

  it("isSuccessStatus is true only for COMPLETE", () => {
    expect(isSuccessStatus("COMPLETE")).toBe(true);
    expect(isSuccessStatus("PAYMENT_FAILED")).toBe(false);
    expect(isSuccessStatus("CANCELLED")).toBe(false);
    expect(isSuccessStatus("INVENTORY_UPDATE_FAILED")).toBe(false);
    expect(isSuccessStatus(null)).toBe(false);
  });
});
