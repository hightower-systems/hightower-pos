import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { isSuccessRefund, useRefund } from "../src/store/refund";

const SAMPLE_LOOKUP = {
  original_transaction_id: "txn-123",
  original_sentry_so_id: "SO-1",
  completed_at: "2026-05-09T18:00:00",
  payment_method: "card",
  card_brand: "VISA",
  card_last4: "4242",
  subtotal_cents: 19999,
  tax_cents: 1620,
  total_cents: 21619,
  lines: [],
  refundable: true,
};

const SAMPLE_RESULT = {
  refund_so_id: "SO-R-1",
  windcave_txn_ref: "WC-R-1",
  card_brand: "VISA",
  card_last4: "4242",
  subtotal_cents: 19999,
  tax_cents: 1620,
  total_cents: 21619,
  payment_method: "card",
  receipt_content: "(refund receipt)",
};

beforeEach(() => useRefund.getState().reset());
afterEach(() => useRefund.getState().reset());

describe("refund store", () => {
  it("starts in idle", () => {
    expect(useRefund.getState().phase).toBe("idle");
    expect(useRefund.getState().original).toBeNull();
  });

  it("openLookup transitions idle -> lookup", () => {
    useRefund.getState().openLookup();
    expect(useRefund.getState().phase).toBe("lookup");
  });

  it("loaded transitions lookup -> confirm and pins the original txn", () => {
    useRefund.getState().openLookup();
    useRefund.getState().loaded(SAMPLE_LOOKUP);
    expect(useRefund.getState().phase).toBe("confirm");
    expect(useRefund.getState().original).toEqual(SAMPLE_LOOKUP);
  });

  it("startedCardRefund transitions confirm -> in_flight with the refund txn id", () => {
    useRefund.getState().openLookup();
    useRefund.getState().loaded(SAMPLE_LOOKUP);
    useRefund.getState().startedCardRefund("refund-txn-1");
    expect(useRefund.getState().phase).toBe("in_flight");
    expect(useRefund.getState().refundTransactionId).toBe("refund-txn-1");
    expect(useRefund.getState().status).toBe("REFUND_PAYMENT_IN_FLIGHT");
  });

  it("finished transitions to result with status + result + error", () => {
    useRefund.getState().finished("COMPLETE", SAMPLE_RESULT, null);
    expect(useRefund.getState().phase).toBe("result");
    expect(useRefund.getState().status).toBe("COMPLETE");
    expect(useRefund.getState().result).toEqual(SAMPLE_RESULT);
  });

  it("failed jumps straight to result with REFUND_PAYMENT_FAILED", () => {
    useRefund.getState().failed("network down");
    expect(useRefund.getState().phase).toBe("result");
    expect(useRefund.getState().status).toBe("REFUND_PAYMENT_FAILED");
    expect(useRefund.getState().error).toBe("network down");
  });

  it("reset clears every field", () => {
    useRefund.getState().loaded(SAMPLE_LOOKUP);
    useRefund.getState().startedCardRefund("refund-txn-1");
    useRefund.getState().finished("COMPLETE", SAMPLE_RESULT, null);
    useRefund.getState().reset();
    const state = useRefund.getState();
    expect(state.phase).toBe("idle");
    expect(state.original).toBeNull();
    expect(state.refundTransactionId).toBeNull();
    expect(state.status).toBeNull();
    expect(state.result).toBeNull();
    expect(state.error).toBeNull();
  });

  it("isSuccessRefund is true only for COMPLETE", () => {
    expect(isSuccessRefund("COMPLETE")).toBe(true);
    expect(isSuccessRefund("REFUND_PAYMENT_FAILED")).toBe(false);
    expect(isSuccessRefund("CANCELLED")).toBe(false);
    expect(isSuccessRefund(null)).toBe(false);
  });
});
