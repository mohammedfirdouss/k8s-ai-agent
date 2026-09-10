"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { getProgress, investigate } from "@/services/api";
import { insforge, insforgeConfigured } from "@/services/insforge";
import type { InvestigateResponse } from "@/types";

// Saves a history row to InsForge. Fire-and-forget: failures never surface.
async function saveHistory(result: InvestigateResponse): Promise<void> {
  if (!insforgeConfigured || !insforge) return;
  try {
    await insforge.database.from("investigations").insert([
      {
        root_cause: result.diagnosis?.root_cause ?? null,
        confidence: result.diagnosis?.confidence ?? null,
        status: result.diagnosis?.error ? "failed" : "completed",
        namespace: null,
      },
    ]);
  } catch {
    // History persistence is best-effort only.
  }
}

// Runs an investigation (long-running POST) and, while it is in flight,
// polls the backend progress endpoint every 800ms.
export function useInvestigate(options?: { onComplete?: () => void }) {
  const mutation = useMutation({
    mutationFn: investigate,
    onSuccess: (data) => {
      void saveHistory(data).then(() => options?.onComplete?.());
    },
  });

  const progressQuery = useQuery({
    queryKey: ["investigate-progress"],
    queryFn: getProgress,
    enabled: mutation.isPending,
    refetchInterval: mutation.isPending ? 800 : false,
    retry: false,
  });

  return { mutation, progress: progressQuery.data };
}
