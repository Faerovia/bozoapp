import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,       // 30s – data jsou čerstvá
      retry: (failureCount, error) => {
        // Neopakuj 401/403/404 – jsou to logické chyby, ne síťové
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const status = (error as any)?.status;
        if ([401, 403, 404].includes(status)) return false;
        return failureCount < 2;
      },
    },
  },
});
