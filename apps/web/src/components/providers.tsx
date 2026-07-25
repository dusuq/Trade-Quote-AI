"use client";

import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            // React Query's default (`networkMode: "online"`) pauses queries
            // indefinitely — leaving the UI stuck with no loading/error
            // feedback — whenever its online-detection heuristic disagrees
            // with actual gateway reachability. "always" makes it attempt
            // every fetch and surface real failures as a real error state,
            // which is what every page here already handles.
            networkMode: "always",
          },
        },
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
