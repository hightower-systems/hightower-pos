export interface WarehouseColor {
  bg: string;
  text: string;
  border: string;
}

const STORE: WarehouseColor = {
  bg: "bg-warehouse-store/15",
  text: "text-warehouse-store",
  border: "border-warehouse-store/40",
};
const AFC: WarehouseColor = {
  bg: "bg-warehouse-afc/15",
  text: "text-warehouse-afc",
  border: "border-warehouse-afc/40",
};
const WEB: WarehouseColor = {
  bg: "bg-warehouse-web/15",
  text: "text-warehouse-web",
  border: "border-warehouse-web/40",
};
const NEUTRAL: WarehouseColor = {
  bg: "bg-surface-card",
  text: "text-ink-muted",
  border: "border-surface-border",
};

export function warehouseColor(warehouse_id: string): WarehouseColor {
  const id = warehouse_id.toUpperCase();
  if (id.includes("STORE")) return STORE;
  if (id.includes("AFC")) return AFC;
  if (id.includes("WEB")) return WEB;
  return NEUTRAL;
}
