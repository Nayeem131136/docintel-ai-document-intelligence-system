import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { isActive } from "./format";

/** Poll every 2 s while anything is still being processed, then stop. */
export function useDocuments(params: Record<string, string | number | undefined>) {
  return useQuery({
    queryKey: ["documents", params],
    queryFn: () => api.documents(params),
    placeholderData: (previous) => previous,
    refetchInterval: (query) => (query.state.data?.results.some((d) => isActive(d.status)) ? 2000 : false),
  });
}

export function useStats() {
  return useQuery({ queryKey: ["stats"], queryFn: api.stats, refetchInterval: 15_000 });
}
