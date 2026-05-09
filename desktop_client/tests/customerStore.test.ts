import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useCustomer } from "../src/store/customer";

const SAMPLE = {
  customer_id: "cust-1",
  name: "Pat Smith",
  email: "pat@example.com",
  phone: "+13035551234",
  registered: true,
};

beforeEach(() => useCustomer.getState().reset());
afterEach(() => useCustomer.getState().reset());

describe("customer store", () => {
  it("starts in idle with no attached customer", () => {
    expect(useCustomer.getState().phase).toBe("idle");
    expect(useCustomer.getState().attached).toBeNull();
  });

  it("openLookup transitions idle -> lookup", () => {
    useCustomer.getState().openLookup();
    expect(useCustomer.getState().phase).toBe("lookup");
  });

  it("setAttached pins the customer and returns phase to idle", () => {
    useCustomer.getState().openLookup();
    useCustomer.getState().setAttached(SAMPLE);
    expect(useCustomer.getState().attached).toEqual(SAMPLE);
    expect(useCustomer.getState().phase).toBe("idle");
  });

  it("detach clears the attached customer but does not open the modal", () => {
    useCustomer.getState().setAttached(SAMPLE);
    useCustomer.getState().detach();
    expect(useCustomer.getState().attached).toBeNull();
    expect(useCustomer.getState().phase).toBe("idle");
  });

  it("reset clears everything back to idle", () => {
    useCustomer.getState().openLookup();
    useCustomer.getState().setAttached(SAMPLE);
    useCustomer.getState().reset();
    expect(useCustomer.getState().phase).toBe("idle");
    expect(useCustomer.getState().attached).toBeNull();
  });
});
