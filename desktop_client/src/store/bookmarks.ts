import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface BookmarkedItem {
  sku: string;
  name: string;
  added_at: string;
}

interface BookmarksState {
  items: BookmarkedItem[];
  add: (sku: string, name: string) => void;
  remove: (sku: string) => void;
  clear: () => void;
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

      clear: () => set({ items: [] }),
    }),
    {
      name: "hightower-pos.bookmarks.v1",
    },
  ),
);
