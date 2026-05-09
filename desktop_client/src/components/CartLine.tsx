import { type CartLine as CartLineType, formatCents, useCart } from "../store/cart";

interface Props {
  line: CartLineType;
}

export function CartLine({ line }: Props) {
  const removeLine = useCart((s) => s.removeLine);
  const setQuantity = useCart((s) => s.setQuantity);

  const lineTotal = line.unit_price_cents * line.quantity;

  return (
    <li className="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-4 rounded-card border border-surface-border bg-surface-card px-4 py-3">
      <div className="min-w-0">
        <div className="font-mono text-sm font-bold text-ink">{line.sku}</div>
        <div className="truncate text-sm text-ink-muted">{line.name}</div>
        <div className="mt-1 flex gap-2 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
          <span className="rounded-badge bg-warehouse-store/15 px-2 py-0.5 text-warehouse-store">
            WH {line.warehouse_name || "-"}
          </span>
          <span className="rounded-badge bg-brand-copper/15 px-2 py-0.5 text-brand-copper">
            BIN {line.bin_name || "-"}
          </span>
        </div>
      </div>

      <input
        type="number"
        min={1}
        value={line.quantity}
        onChange={(event) =>
          setQuantity(line.id, parseInt(event.target.value, 10) || 1)
        }
        onFocus={(event) => event.target.select()}
        aria-label={`Quantity for ${line.sku}`}
        className="w-16 rounded-card border border-surface-inputBorder bg-surface-input px-2 py-1 text-center font-mono text-base text-ink outline-none focus:border-brand-red"
      />

      <span className="font-mono text-sm text-ink-muted">
        {formatCents(line.unit_price_cents)}
      </span>

      <span className="min-w-[80px] text-right font-mono text-sm font-bold text-ink">
        {formatCents(lineTotal)}
      </span>

      <button
        type="button"
        onClick={() => removeLine(line.id)}
        aria-label={`Remove ${line.sku}`}
        className="rounded-card border border-surface-border bg-surface px-2 py-1 font-mono text-sm font-bold text-ink-muted hover:bg-status-danger/10 hover:text-status-danger"
      >
        ×
      </button>
    </li>
  );
}
