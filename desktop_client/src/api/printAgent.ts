import { useQuery } from "@tanstack/react-query";

export interface PrintAgentStatus {
  agent_status: string;
  agent_version: string;
  printer_online: boolean;
  last_print_at: string | null;
}

const PRINT_AGENT_BASE = "/print-agent";

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
