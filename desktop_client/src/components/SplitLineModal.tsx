import { useEffect, useState } from "react";

import { type CartLine, type SplitSpec, useCart } from "../store/cart";
import { Modal } from "./Modal";
import { warehouseColor } from "./warehouseColor";

interface Props {
  open: boolean;
  onClose: () => void;
  line: CartLine;
}

interface SplitRow {
  warehouse_id: string;
  warehouse_name: string;
  bin_id: string;
  qty: number;
  qty_available: number;
}

function buildInitialRows(line: CartLine): SplitRow[] {
  return line.availability.map((wh) => {
    const bin = wh.bins.find((b) => b.qty > 0) ?? wh.bins[0];
    const isOriginal = wh.warehouse_id === line.warehouse_id;
    return {
      warehouse_id: wh.warehouse_id,
      warehouse_name: wh.warehouse_name,
      bin_id: isOriginal ? line.bin_id : bin?.bin_id ?? "",
      qty: isOriginal ? line.quantity : 0,
      qty_available: wh.qty_available,
    };
  });
}

export function SplitLineModal({ open, onClose, line }: Props) {
  const splitLine = useCart((s) => s.splitLine);
  const [rows, setRows] = useState<SplitRow[]>(() => buildInitialRows(line));

  useEffect(() => {
    if (open) setRows(buildInitialRows(line));
  }, [open, line]);

  const total = rows.reduce((sum, r) => sum + r.qty, 0);
  const target = line.quantity;
  const isValid = total === target && rows.some((r) => r.qty > 0);

  function setRowQty(warehouse_id: string, qty: number) {
    setRows((prev) =>
      prev.map((r) =>
        r.warehouse_id === warehouse_id
          ? { ...r, qty: Math.max(0, qty) }
          : r,
      ),
    );
  }

  function handleSave() {
    if (!isValid) return;
    const splits: SplitSpec[] = rows
      .filter((r) => r.qty > 0)
      .map((r) => ({
        warehouse_id: r.warehouse_id,
        bin_id: r.bin_id,
        quantity: r.qty,
      }));
    splitLine(line.id, splits);
    onClose();
  }

  return (
    <Modal open={open} onClose={onClose} title={`Split ${line.sku}`}>
      <p className="mb-3 font-mono text-xs uppercase tracking-wider text-ink-muted">
        How many from each warehouse? Sum must equal {target}.
      </p>

      <ul className="flex flex-col gap-2" aria-label="Split rows">
        {rows.map((row) => {
          const color = warehouseColor(row.warehouse_id);
          return (
            <li
              key={row.warehouse_id}
              className={`flex items-center justify-between rounded-card border ${color.border} ${color.bg} px-4 py-3`}
            >
              <div className="flex flex-col">
                <span
                  className={`font-mono text-sm font-bold uppercase tracking-wider ${color.text}`}
                >
                  {row.warehouse_name}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-wider text-ink-soft">
                  {row.qty_available} avail
                </span>
              </div>
              <input
                type="number"
                min={0}
                value={row.qty}
                onChange={(event) =>
                  setRowQty(
                    row.warehouse_id,
                    parseInt(event.target.value, 10) || 0,
                  )
                }
                onFocus={(event) => event.target.select()}
                aria-label={`Quantity from ${row.warehouse_name}`}
                className="w-20 rounded-card border border-surface-inputBorder bg-surface px-2 py-1 text-center font-mono text-base text-ink outline-none focus:border-brand-red"
              />
            </li>
          );
        })}
      </ul>

      <div
        data-testid="split-total"
        className={`mt-4 flex items-baseline justify-between border-t border-surface-border pt-3 font-mono text-sm uppercase tracking-wider ${isValid ? "text-status-success" : "text-status-warning"}`}
      >
        <span>Total</span>
        <span>
          {total} / {target}
          {isValid ? " ok" : ""}
        </span>
      </div>

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 rounded-card border border-surface-border bg-surface px-4 py-2 font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted hover:bg-surface-card"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={!isValid}
          className="flex-1 rounded-card bg-brand-red px-4 py-2 font-mono text-xs font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Save split
        </button>
      </div>
    </Modal>
  );
}
