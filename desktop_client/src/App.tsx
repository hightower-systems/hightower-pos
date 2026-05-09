import { useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchMe } from "./api/auth";
import { ApiError } from "./api/client";
import { LoginScreen } from "./screens/LoginScreen";
import { RegisterScreen } from "./screens/RegisterScreen";

export default function App() {
  const queryClient = useQueryClient();
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

  return (
    <RegisterScreen
      user={data}
      onSignedOut={() => {
        queryClient.removeQueries({ queryKey: ["me"] });
        void refetch();
      }}
    />
  );
}
