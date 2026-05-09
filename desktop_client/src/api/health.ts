import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

export interface SentryHealth {
  reachable: boolean;
  latency_ms: number | null;
  error: string | null;
}

export interface WindcaveHealth {
  configured: boolean;
  mock: boolean;
}

export interface DependenciesResponse {
  version: string;
  terminal_id: string;
  sentry: SentryHealth;
  windcave: WindcaveHealth;
}

export function useDependencies(enabled = true) {
  return useQuery({
    queryKey: ["dependencies"],
    queryFn: () => api<DependenciesResponse>("/api/health/dependencies"),
    refetchInterval: 10_000,
    staleTime: 5_000,
    enabled,
  });
}
