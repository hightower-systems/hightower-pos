import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useBookmarks } from "../src/store/bookmarks";

beforeEach(() => useBookmarks.getState().clear());
afterEach(() => useBookmarks.getState().clear());

describe("bookmark store", () => {
  it("starts empty", () => {
    expect(useBookmarks.getState().items).toEqual([]);
  });

  it("add inserts a new SKU with name", () => {
    useBookmarks.getState().add("ROD-100", "Premium Fly Rod");
    const items = useBookmarks.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0].sku).toBe("ROD-100");
    expect(items[0].name).toBe("Premium Fly Rod");
  });

  it("add deduplicates -- second add for the same SKU is a no-op", () => {
    useBookmarks.getState().add("ROD-100", "Premium Fly Rod");
    useBookmarks.getState().add("ROD-100", "Different Name");
    const items = useBookmarks.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0].name).toBe("Premium Fly Rod");
  });

  it("add ignores empty SKUs", () => {
    useBookmarks.getState().add("   ", "");
    expect(useBookmarks.getState().items).toEqual([]);
  });

  it("add falls back name to SKU when name is empty", () => {
    useBookmarks.getState().add("ROD-100", "");
    expect(useBookmarks.getState().items[0].name).toBe("ROD-100");
  });

  it("remove deletes by SKU", () => {
    useBookmarks.getState().add("ROD-100", "Rod");
    useBookmarks.getState().add("REEL-200", "Reel");
    useBookmarks.getState().remove("ROD-100");
    const items = useBookmarks.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0].sku).toBe("REEL-200");
  });

  it("clear empties the store", () => {
    useBookmarks.getState().add("ROD-100", "Rod");
    useBookmarks.getState().add("REEL-200", "Reel");
    useBookmarks.getState().clear();
    expect(useBookmarks.getState().items).toEqual([]);
  });
});
