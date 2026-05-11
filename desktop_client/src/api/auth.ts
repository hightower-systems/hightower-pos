import { useMutation } from "@tanstack/react-query";

import { api } from "./client";
import type { TillSessionBrief } from "./till";

export interface UserInfo {
  username: string;
  display_name: string;
  expires_at: string;
  must_change_password: boolean;
  // Present when the cashier has an OPEN till at login/me time.
  // null otherwise -- the RegisterScreen gates on this and shows
  // the OpenTillModal until the cashier opens a till.
  till_session?: TillSessionBrief | null;
}

export interface LogoutResponse {
  logged_out: boolean;
  // Server flags open_till_session when the cashier logs out
  // without closing first. Doesn't block the logout, just gives
  // the client the chance to surface a 'close it next time' confirm.
  warning?: string | null;
  session_id?: string | null;
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
      api<LogoutResponse>("/api/auth/logout", { method: "POST" }),
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
