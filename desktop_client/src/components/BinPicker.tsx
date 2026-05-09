import { type CartLine, useCart } from "../store/cart";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  line: CartLine;
}

export function BinPicker({ open, onClose, line }: Props) {
  const setWarehouseBin = useCart((s) => s.setWarehouseBin);
  const wh = line.availability.find(
    (w) => w.warehouse_id === line.warehouse_id,
  );

  function pickBin(bin_id: string) {
    setWarehouseBin(line.id, line.warehouse_id, bin_id);
    onClose();
  }

  return (
    <Modal open={open} onClose={onClose} title={`Bin in ${wh?.warehouse_name ?? "warehouse"}`}>
      {!wh || wh.bins.length === 0 ? (
        <p className="font-mono text-xs uppercase tracking-wider text-ink-soft">
          No bins on file for this warehouse.
        </p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Bin options">
          {wh.bins.map((bin) => {
            const isSelected = bin.bin_id === line.bin_id;
            return (
              <li key={bin.bin_id}>
                <button
                  type="button"
                  onClick={() => pickBin(bin.bin_id)}
                  aria-pressed={isSelected}
                  className={`flex w-full items-center justify-between rounded-card border border-surface-border bg-surface-card px-4 py-3 text-left transition ${isSelected ? "ring-2 ring-brand-red" : "hover:brightness-95"}`}
                >
                  <span className="font-mono text-sm font-bold uppercase tracking-wider text-brand-copper">
                    BIN {bin.bin_name}
                  </span>
                  <span className="font-mono text-base font-bold text-ink">
                    {bin.qty}
                    <span className="ml-1 text-[10px] uppercase tracking-wider text-ink-soft">
                      in bin
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Modal>
  );
}
