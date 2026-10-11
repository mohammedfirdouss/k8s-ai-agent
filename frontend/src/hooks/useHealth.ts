"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/services/api";

// Backend liveness, re-checked every 30s so the header badge stays current.
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 30_000,
    retry: false,
  });
}
