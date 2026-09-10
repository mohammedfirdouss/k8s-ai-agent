"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/services/api";

// Placeholder hook: fetches backend health via React Query.
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
  });
}
