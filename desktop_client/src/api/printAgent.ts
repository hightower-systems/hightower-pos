import { useMutation, useQuery } from "@tanstack/react-query";

export interface PrintAgentStatus {
  agent_status: string;
  agent_version: string;
  printer_online: boolean;
  last_print_at: string | null;
}

export interface PrintReceiptArgs {
  content: string;
  open_drawer_after?: boolean;
  cut?: boolean;
}

export interface PrintResponse {
  success: boolean;
  printer_status: string;
}

export interface DrawerResponse {
  success: boolean;
}

const PRINT_AGENT_BASE = "/print-agent";

async function postAgent<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${PRINT_AGENT_BASE}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`print agent ${path} ${response.status}`);
  }
  return (await response.json()) as T;
}

async function fetchAgentStatus(): Promise<PrintAgentStatus> {
  const response = await fetch(`${PRINT_AGENT_BASE}/status`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`print agent status ${response.status}`);
  }
  return (await response.json()) as PrintAgentStatus;
}

export function usePrintAgentStatus(enabled = true) {
  return useQuery({
    queryKey: ["printAgentStatus"],
    queryFn: fetchAgentStatus,
    refetchInterval: 10_000,
    staleTime: 5_000,
    retry: false,
    enabled,
  });
}

export function usePrintReceipt() {
  return useMutation<PrintResponse, Error, PrintReceiptArgs>({
    mutationFn: ({ content, open_drawer_after = false, cut = true }) =>
      postAgent<PrintResponse>("/print", {
        format: "text",
        content,
        cut,
        open_drawer_after,
      }),
  });
}

export function useOpenDrawer() {
  return useMutation<DrawerResponse, Error, void>({
    mutationFn: () => postAgent<DrawerResponse>("/open-drawer"),
  });
}
