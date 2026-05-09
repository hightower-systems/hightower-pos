import { useState } from "react";

import { type CartLine as CartLineType, formatCents, useCart } from "../store/cart";
import { BinPicker } from "./BinPicker";
import { SplitLineModal } from "./SplitLineModal";
import { WarehousePicker } from "./WarehousePicker";
import { warehouseColor } from "./warehouseColor";

interface Props {
  line: CartLineType;
}

type OpenPicker = "warehouse" | "bin" | "split" | null;

export function CartLine({ line }: Props) {
  const removeLine = useCart((s) => s.removeLine);
  const setQuantity = useCart((s) => s.setQuantity);
  const [picker, setPicker] = useState<OpenPicker>(null);

  const lineTotal = line.unit_price_cents * line.quantity;
  const wh = line.availability.find((w) => w.warehouse_id === line.warehouse_id);
  const bin = wh?.bins.find((b) => b.bin_id === line.bin_id);
  const binQty = bin?.qty ?? 0;
  const oversold = line.quantity > binQty;
  const whColor = warehouseColor(line.warehouse_id);

  return (
    <li className="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-4 rounded-card border border-surface-border bg-surface-card px-4 py-3">
      <div className="min-w-0">
        <div className="font-mono text-sm font-bold text-ink">{line.sku}</div>
        <div className="truncate text-sm text-ink-muted">{line.name}</div>
        <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-wider">
          <button
            type="button"
            onClick={() => setPicker("warehouse")}
            aria-label={`Change warehouse for ${line.sku}`}
            className={`rounded-badge border px-2 py-0.5 ${whColor.bg} ${whColor.border} ${whColor.text} hover:brightness-95`}
          >
            WH {line.warehouse_name || "-"}
          </button>
          <button
            type="button"
            onClick={() => setPicker("bin")}
            aria-label={`Change bin for ${line.sku}`}
            className="rounded-badge border border-brand-copper/40 bg-brand-copper/15 px-2 py-0.5 text-brand-copper hover:brightness-95"
          >
            BIN {line.bin_name || "-"}
          </button>
          {line.availability.length > 1 && (
            <button
              type="button"
              onClick={() => setPicker("split")}
              aria-label={`Split ${line.sku}`}
              className="rounded-badge border border-surface-border bg-surface px-2 py-0.5 text-ink-muted hover:bg-surface-card"
            >
              Split
            </button>
          )}
          {oversold && (
            <span
              role="status"
              data-testid="oversold-warning"
              className="rounded-badge border border-status-warning/50 bg-status-warning/15 px-2 py-0.5 text-status-warning"
            >
              {binQty === 0
                ? "Out of stock here"
                : `Only ${binQty} in bin`}
            </span>
          )}
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

      <WarehousePicker
        open={picker === "warehouse"}
        onClose={() => setPicker(null)}
        line={line}
      />
      <BinPicker
        open={picker === "bin"}
        onClose={() => setPicker(null)}
        line={line}
      />
      <SplitLineModal
        open={picker === "split"}
        onClose={() => setPicker(null)}
        line={line}
      />
    </li>
  );
}
