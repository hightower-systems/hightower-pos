import { useCart } from "../store/cart";
import { CartLine } from "./CartLine";

export function Cart() {
  const lines = useCart((s) => s.lines);

  if (lines.length === 0) {
    return (
      <div className="flex h-full min-h-[160px] items-center justify-center rounded-card border border-dashed border-surface-border bg-surface-card/50 text-center">
        <p className="font-mono text-xs uppercase tracking-wider text-ink-soft">
          Cart is empty. Scan an item to start.
        </p>
      </div>
    );
  }

  return (
    <ul className="flex flex-col gap-2" aria-label="Cart">
      {lines.map((line) => (
        <CartLine key={line.id} line={line} />
      ))}
    </ul>
  );
}
