import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "./client";

export interface UserSummary {
  username: string;
  display_name: string;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
}

export interface CreateUserRequest {
  username: string;
  display_name: string;
  initial_password: string;
}

export function useUsers() {
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => api<{ users: UserSummary[] }>("/api/admin/users"),
  });
}

export function useCreateUser() {
  return useMutation({
    mutationFn: (body: CreateUserRequest) =>
      api<UserSummary>("/api/admin/users", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function useDeactivateUser() {
  return useMutation({
    mutationFn: (username: string) =>
      api<UserSummary>(`/api/admin/users/${encodeURIComponent(username)}`, {
        method: "DELETE",
      }),
  });
}

export function useResetUserPassword() {
  return useMutation({
    mutationFn: ({
      username,
      new_password,
    }: {
      username: string;
      new_password: string;
    }) =>
      api<UserSummary>(
        `/api/admin/users/${encodeURIComponent(username)}/reset-password`,
        {
          method: "POST",
          body: JSON.stringify({ new_password }),
        },
      ),
  });
}
