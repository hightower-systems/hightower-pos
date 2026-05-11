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
// time. Each color drives:
//   - the wraparound border on the bookmark card (BORDER_CLASS)
//   - the corresponding small swatch button shown in the card's
//     top-left corner for click-cycle (SWATCH_CLASS)
//
// 'none' is the unset state: the card uses the default neutral
// surface border so unmarked bookmarks don't fight for attention,
// while the swatch shows a dashed-outline empty circle.
const BORDER_CLASS: Record<BookmarkColor, string> = {
  none: "border-surface-border",
  red: "border-red-500",
  orange: "border-orange-500",
  yellow: "border-yellow-400",
  green: "border-green-500",
  blue: "border-blue-500",
  indigo: "border-indigo-500",
  violet: "border-violet-500",
};

const SWATCH_CLASS: Record<BookmarkColor, string> = {
  none: "bg-surface border-surface-border border-dashed",
  red: "bg-red-500 border-red-500",
  orange: "bg-orange-500 border-orange-500",
  yellow: "bg-yellow-400 border-yellow-400",
  green: "bg-green-500 border-green-500",
  blue: "bg-blue-500 border-blue-500",
  indigo: "bg-indigo-500 border-indigo-500",
  violet: "bg-violet-500 border-violet-500",
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
                  data-testid={`bookmark-card-${bookmark.sku}`}
                  data-color={color}
                  // border-[3px] always so colored vs neutral states
                  // don't shift the card size. The whole bubble shows
                  // the current color via this wraparound border.
                  className={`relative overflow-hidden rounded-card border-[3px] bg-surface transition-colors ${BORDER_CLASS[color]}`}
                >
                  <button
                    type="button"
                    onClick={() => handleAdd(bookmark)}
                    disabled={lookup.isPending}
                    aria-label={`Add ${bookmark.sku} to cart`}
                    className="flex h-full w-full flex-col items-start gap-1 px-3 pb-3 pt-7 text-left hover:bg-brand-red/5 focus:outline-none focus:ring-2 focus:ring-brand-red focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
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
                    onClick={() => cycleColor(bookmark.sku)}
                    aria-label={`Cycle color for ${bookmark.sku} (current: ${color})`}
                    title="Click to color-tag this bookmark"
                    data-testid={`bookmark-swatch-${bookmark.sku}`}
                    className={`absolute left-1.5 top-1.5 h-4 w-4 rounded-full border-2 transition hover:scale-110 ${SWATCH_CLASS[color]}`}
                  />
                  <button
                    type="button"
                    onClick={() => remove(bookmark.sku)}
                    aria-label={`Remove ${bookmark.sku} from bookmarks`}
                    className="absolute right-1 top-1 rounded-badge border border-surface-border bg-surface px-1.5 font-mono text-[10px] text-ink-muted hover:bg-status-danger/10 hover:text-status-danger"
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
