import { type FormEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { useItemLookup } from "../api/items";
import { useCart } from "../store/cart";

const ERROR_LABELS: Record<string, string> = {
  item_not_found: "Item not found.",
  exactly_one_identifier_required: "Scan a barcode or SKU.",
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

export function ScanInput() {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const lookup = useItemLookup();
  const addItem = useCart((s) => s.addItem);

  // Always-focused: any click that isn't on an editable control or a
  // button refocuses the scan input. Cashiers want barcodes to land here
  // even after they've clicked away to look at totals or a cart line.
  useEffect(() => {
    const handler = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target) return;
      const tag = target.tagName;
      if (tag === "INPUT" || tag === "BUTTON" || tag === "TEXTAREA" || tag === "SELECT") {
        return;
      }
      inputRef.current?.focus();
    };
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, []);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const term = value.trim();
    if (!term) return;
    setError(null);
    lookup.mutate(
      { barcode: term },
      {
        onSuccess: (item) => {
          addItem(item);
          setValue("");
        },
        onError: (err) => {
          setError(friendlyError(err));
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Scan item">
      <label className="mb-1 block font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted">
        Scan
      </label>
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Scan barcode or type SKU"
        autoFocus
        disabled={lookup.isPending}
        aria-label="Scan barcode or SKU"
        className="w-full rounded-card border border-surface-inputBorder bg-surface-input px-4 py-3 font-mono text-lg text-ink outline-none focus:border-brand-red disabled:opacity-60"
      />
      {error && (
        <p
          role="alert"
          className="mt-2 rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-status-danger"
        >
          {error}
        </p>
      )}
    </form>
  );
}
