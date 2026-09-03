import { useQuery } from "@tanstack/react-query";

import {
  AUTH_QUERY_KEY,
  getAuthState,
} from "../../shared/api/auth";

export function useAuthState() {
  return useQuery({
    queryKey: AUTH_QUERY_KEY,
    queryFn: ({ signal }) => getAuthState(signal),
    enabled: false,
    staleTime: 60_000,
  });
}
