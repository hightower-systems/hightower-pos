import { type CartLine, useCart } from "../store/cart";
import { Modal } from "./Modal";
import { warehouseColor } from "./warehouseColor";

interface Props {
  open: boolean;
  onClose: () => void;
  line: CartLine;
}

export function WarehousePicker({ open, onClose, line }: Props) {
  const setWarehouseBin = useCart((s) => s.setWarehouseBin);

  function pickWarehouse(warehouse_id: string) {
    const wh = line.availability.find((w) => w.warehouse_id === warehouse_id);
    if (!wh) return;
    const bin = wh.bins.find((b) => b.qty > 0) ?? wh.bins[0];
    setWarehouseBin(line.id, warehouse_id, bin?.bin_id ?? "");
    onClose();
  }

  return (
    <Modal open={open} onClose={onClose} title={`Warehouse for ${line.sku}`}>
      <ul className="flex flex-col gap-2" aria-label="Warehouse options">
        {line.availability.map((wh) => {
          const isSelected = wh.warehouse_id === line.warehouse_id;
          const color = warehouseColor(wh.warehouse_id);
          return (
            <li key={wh.warehouse_id}>
              <button
                type="button"
                onClick={() => pickWarehouse(wh.warehouse_id)}
                aria-pressed={isSelected}
                className={`flex w-full items-center justify-between rounded-card border px-4 py-3 text-left transition ${color.bg} ${color.border} ${isSelected ? "ring-2 ring-brand-red" : "hover:brightness-95"}`}
              >
                <div className="flex flex-col">
                  <span className={`font-mono text-sm font-bold uppercase tracking-wider ${color.text}`}>
                    {wh.warehouse_name}
                  </span>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-ink-soft">
                    {wh.warehouse_id}
                  </span>
                </div>
                <span className="font-mono text-base font-bold text-ink">
                  {wh.qty_available}
                  <span className="ml-1 text-[10px] uppercase tracking-wider text-ink-soft">
                    avail
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </Modal>
  );
}
