import { useQuery } from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api";
import type { Profile } from "@/lib/types";

export const profileKey = ["dashboard", "me"];

export function useProfile() {
  return useQuery({
    queryKey: profileKey,
    queryFn: () => api.get<Profile>("/api/dashboard/me"),
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
    staleTime: 60_000,
  });
}
