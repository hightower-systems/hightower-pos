import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchMe, type UserInfo } from "./api/auth";
import { ApiError } from "./api/client";
import { ChangePasswordScreen } from "./screens/ChangePasswordScreen";
import { LoginScreen } from "./screens/LoginScreen";
import { RegisterScreen } from "./screens/RegisterScreen";
import { SettingsScreen } from "./screens/SettingsScreen";

type View = "register" | "settings";

export default function App() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<View>("register");
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    retry: false,
    refetchOnWindowFocus: true,
  });

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface font-mono text-sm uppercase tracking-wider text-ink-muted">
        Loading...
      </div>
    );
  }

  const isUnauthenticated =
    isError && error instanceof ApiError && error.status === 401;
  if (isUnauthenticated || !data) {
    return (
      <LoginScreen
        onSuccess={() => {
          void refetch();
        }}
      />
    );
  }

  if (data.must_change_password) {
    return (
      <ChangePasswordScreen
        user={data}
        onChanged={(updated: UserInfo) => {
          queryClient.setQueryData(["me"], updated);
        }}
        onSignedOut={() => {
          queryClient.removeQueries({ queryKey: ["me"] });
          void refetch();
        }}
      />
    );
  }

  if (view === "settings") {
    return (
      <SettingsScreen
        user={data}
        onBack={() => setView("register")}
      />
    );
  }

  return (
    <RegisterScreen
      user={data}
      onOpenSettings={() => setView("settings")}
      onSignedOut={() => {
        queryClient.removeQueries({ queryKey: ["me"] });
        setView("register");
        void refetch();
      }}
    />
  );
}
