import { describe, expect, it } from "vitest";

import { warehouseColor } from "../src/components/warehouseColor";

describe("warehouseColor", () => {
  it("matches STORE warehouses to the warehouse-store palette", () => {
    expect(warehouseColor("WH-STORE").text).toBe("text-warehouse-store");
    expect(warehouseColor("store-1").text).toBe("text-warehouse-store");
  });

  it("matches AFC warehouses to the warehouse-afc palette", () => {
    expect(warehouseColor("WH-AFC").text).toBe("text-warehouse-afc");
  });

  it("matches WEB warehouses to the warehouse-web palette", () => {
    expect(warehouseColor("WH-WEB").text).toBe("text-warehouse-web");
  });

  it("returns the neutral palette for unknown warehouse ids", () => {
    expect(warehouseColor("UNKNOWN-1").text).toBe("text-ink-muted");
    expect(warehouseColor("").text).toBe("text-ink-muted");
  });
});
