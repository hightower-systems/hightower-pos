import { create } from "zustand";

export interface AttachedCustomer {
  customer_id: string | null;
  name: string | null;
  email: string | null;
  phone: string | null;
  registered: boolean;
}

export type CustomerPhase = "idle" | "lookup";

interface CustomerState {
  phase: CustomerPhase;
  attached: AttachedCustomer | null;
  openLookup: () => void;
  closeLookup: () => void;
  setAttached: (customer: AttachedCustomer) => void;
  detach: () => void;
  reset: () => void;
}

export const useCustomer = create<CustomerState>((set) => ({
  phase: "idle",
  attached: null,

  openLookup: () => set({ phase: "lookup" }),
  closeLookup: () => set({ phase: "idle" }),
  setAttached: (customer) => set({ attached: customer, phase: "idle" }),
  detach: () => set({ attached: null }),
  reset: () => set({ phase: "idle", attached: null }),
}));
