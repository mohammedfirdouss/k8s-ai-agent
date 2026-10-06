"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { getProgress, investigate } from "@/services/api";

// Runs an investigation (long-running POST) and, while it is in flight,
// polls that investigation's progress endpoint every 800ms. The backend
// saves the result to history itself.
export function useInvestigate(options?: { onComplete?: () => void }) {
  const [investigationId, setInvestigationId] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: ({ id, context }: { id: string; context?: string | null }) =>
      investigate(id, context),
    onSuccess: () => options?.onComplete?.(),
  });

  const progressQuery = useQuery({
    queryKey: ["investigate-progress", investigationId],
    queryFn: () => getProgress(investigationId!),
    enabled: mutation.isPending && investigationId !== null,
    refetchInterval: mutation.isPending ? 800 : false,
    // Keep polling if the user switches tabs during a long investigation.
    refetchIntervalInBackground: true,
    retry: false,
  });

  function start(context?: string | null) {
    const id = crypto.randomUUID();
    setInvestigationId(id);
    mutation.mutate({ id, context });
  }

  return { mutation, start, progress: progressQuery.data };
}
