import { useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { useItemLookup } from "../api/items";
import { useCart } from "../store/cart";
import {
  type BookmarkColor,
  type BookmarkedItem,
  useBookmarks,
} from "../store/bookmarks";

// Tailwind class per color name. Kept static (not built from a
// template string) so the JIT purge picks up every class at build
// time. 'none' renders as a thin neutral divider so the bar still
// reads as 'clickable target' even before a color is picked.
const COLOR_BAR_CLASS: Record<BookmarkColor, string> = {
  // 'none' is the unset state. A diagonal-stripe SVG pattern reads
  // as 'clickable but blank' so the affordance is discoverable even
  // before the cashier has picked a color (prior solid grey looked
  // identical to the card border and disappeared).
  none:
    "bg-[repeating-linear-gradient(45deg,_theme(colors.surface.border)_0,_theme(colors.surface.border)_4px,_theme(colors.surface.card)_4px,_theme(colors.surface.card)_8px)]",
  red: "bg-red-500",
  orange: "bg-orange-500",
  yellow: "bg-yellow-400",
  green: "bg-green-500",
  blue: "bg-blue-500",
  indigo: "bg-indigo-500",
  violet: "bg-violet-500",
};

const ERROR_LABELS: Record<string, string> = {
  item_not_found: "Item not found.",
  price_missing: "No price on file for this SKU.",
  sentry_unavailable: "Inventory service is offline.",
};

function friendlyError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code && ERROR_LABELS[error.code]) {
      return ERROR_LABELS[error.code];
    }
    if (error.status === 404) return "Item not found.";
  }
  return "Could not reach the POS service.";
}

export function BookmarkPane() {
  const bookmarks = useBookmarks((s) => s.items);
  const remove = useBookmarks((s) => s.remove);
  const cycleColor = useBookmarks((s) => s.cycleColor);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const lookup = useItemLookup();
  const addItem = useCart((s) => s.addItem);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return bookmarks;
    return bookmarks.filter(
      (b) =>
        b.sku.toLowerCase().includes(q) ||
        b.name.toLowerCase().includes(q),
    );
  }, [bookmarks, filter]);

  function handleAdd(bookmark: BookmarkedItem) {
    setError(null);
    lookup.mutate(
      { sku: bookmark.sku },
      {
        onSuccess: (item) => {
          addItem(item);
        },
        onError: (err) => {
          setError(`${bookmark.sku}: ${friendlyError(err)}`);
        },
      },
    );
  }

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-ink-muted">
          Bookmarks
        </h2>
        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-soft">
          {bookmarks.length} item{bookmarks.length === 1 ? "" : "s"}
        </span>
      </div>

      <input
        type="text"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        placeholder="Filter SKU or name"
        aria-label="Filter bookmarks"
        className="w-full rounded-card border border-surface-inputBorder bg-surface px-3 py-2 font-mono text-sm text-ink outline-none focus:border-brand-red"
      />

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-status-danger"
        >
          <span className="flex-1">{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            aria-label="Dismiss bookmark error"
            className="text-status-danger"
          >
            ×
          </button>
        </div>
      )}

      <div className="flex-1 overflow-auto">
        {bookmarks.length === 0 ? (
          <div
            data-testid="bookmarks-empty"
            className="flex h-full items-center justify-center rounded-card border border-dashed border-surface-border p-4 text-center"
          >
            <p className="font-mono text-[10px] uppercase tracking-wider text-ink-soft">
              No bookmarks yet. Use the star on a cart line to keep a SKU here.
            </p>
          </div>
        ) : filtered.length === 0 ? (
          <p className="p-2 font-mono text-[10px] uppercase tracking-wider text-ink-soft">
            No bookmarks match "{filter}".
          </p>
        ) : (
          <ul className="grid grid-cols-2 gap-2" aria-label="Bookmarks">
            {filtered.map((bookmark) => {
              const color = bookmark.color ?? "none";
              return (
                <li
                  key={bookmark.sku}
                  className="relative overflow-hidden rounded-card border border-surface-border bg-surface"
                >
                  <button
                    type="button"
                    onClick={() => cycleColor(bookmark.sku)}
                    aria-label={`Cycle color for ${bookmark.sku} (current: ${color})`}
                    title="Click to color-tag this bookmark"
                    className={`block h-2.5 w-full transition-all hover:brightness-110 ${COLOR_BAR_CLASS[color]}`}
                  />
                  <button
                    type="button"
                    onClick={() => handleAdd(bookmark)}
                    disabled={lookup.isPending}
                    aria-label={`Add ${bookmark.sku} to cart`}
                    className="flex h-full w-full flex-col items-start gap-1 p-3 text-left hover:bg-brand-red/5 focus:outline-none focus:ring-2 focus:ring-brand-red focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <span className="line-clamp-2 text-sm font-bold leading-tight text-ink">
                      {bookmark.name}
                    </span>
                    <span className="font-mono text-[10px] font-semibold text-ink-muted">
                      {bookmark.sku}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(bookmark.sku)}
                    aria-label={`Remove ${bookmark.sku} from bookmarks`}
                    className="absolute right-1 top-2.5 rounded-badge border border-surface-border bg-surface px-1.5 font-mono text-[10px] text-ink-muted hover:bg-status-danger/10 hover:text-status-danger"
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
