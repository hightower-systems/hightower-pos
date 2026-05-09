import { useMutation } from "@tanstack/react-query";

import { api } from "./client";

export interface UserInfo {
  username: string;
  display_name: string;
  expires_at: string;
  must_change_password: boolean;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export function fetchMe(): Promise<UserInfo> {
  return api<UserInfo>("/api/auth/me");
}

export function useLogin() {
  return useMutation({
    mutationFn: (body: LoginRequest) =>
      api<UserInfo>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: () =>
      api<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: ChangePasswordRequest) =>
      api<UserInfo>("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}
