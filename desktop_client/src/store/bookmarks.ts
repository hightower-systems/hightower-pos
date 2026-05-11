import { create } from "zustand";
import { persist } from "zustand/middleware";

// Rainbow palette for the bookmark color bar. Order is ROYGBIV +
// 'none' so clicking the bar cycles through a familiar progression.
// 'none' is the unset state -- new bookmarks land here and the bar
// renders as a thin neutral divider.
export const BOOKMARK_COLORS = [
  "none",
  "red",
  "orange",
  "yellow",
  "green",
  "blue",
  "indigo",
  "violet",
] as const;

export type BookmarkColor = (typeof BOOKMARK_COLORS)[number];

export interface BookmarkedItem {
  sku: string;
  name: string;
  added_at: string;
  // Optional so existing persisted bookmarks (pre-color-bar feature)
  // load without migration -- missing field reads as 'none'.
  color?: BookmarkColor;
}

interface BookmarksState {
  items: BookmarkedItem[];
  add: (sku: string, name: string) => void;
  remove: (sku: string) => void;
  cycleColor: (sku: string) => void;
  clear: () => void;
}

function nextColor(current: BookmarkColor | undefined): BookmarkColor {
  const idx = BOOKMARK_COLORS.indexOf((current ?? "none") as BookmarkColor);
  return BOOKMARK_COLORS[(idx + 1) % BOOKMARK_COLORS.length];
}

export const useBookmarks = create<BookmarksState>()(
  persist(
    (set, get) => ({
      items: [],

      add: (sku, name) => {
        const trimmedSku = sku.trim();
        if (!trimmedSku) return;
        if (get().items.some((b) => b.sku === trimmedSku)) return;
        set((state) => ({
          items: [
            ...state.items,
            { sku: trimmedSku, name: name.trim() || trimmedSku, added_at: new Date().toISOString() },
          ],
        }));
      },

      remove: (sku) =>
        set((state) => ({
          items: state.items.filter((b) => b.sku !== sku),
        })),

      cycleColor: (sku) =>
        set((state) => ({
          items: state.items.map((b) =>
            b.sku === sku ? { ...b, color: nextColor(b.color) } : b,
          ),
        })),

      clear: () => set({ items: [] }),
    }),
    {
      name: "hightower-pos.bookmarks.v1",
    },
  ),
);
