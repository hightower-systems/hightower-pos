import { useMutation } from "@tanstack/react-query";

import { api } from "./client";

export interface CustomerLookupResponse {
  customer_id: string | null;
  display_name: string | null;
  email: string | null;
  phone: string | null;
  registered: boolean;
}

export interface CustomerLookupArgs {
  name?: string;
  email?: string;
  phone?: string;
}

export function useCustomerLookup() {
  return useMutation<CustomerLookupResponse | null, Error, CustomerLookupArgs>({
    mutationFn: async ({ name, email, phone }) => {
      const params = new URLSearchParams();
      if (name) params.set("name", name);
      if (email) params.set("email", email);
      if (phone) params.set("phone", phone);
      return api<CustomerLookupResponse | null>(
        `/api/customers/lookup?${params.toString()}`,
      );
    },
  });
}
