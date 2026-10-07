"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { getInvestigation, startInvestigation } from "@/services/api";

// Per-tab memory of the investigation being watched, so a page refresh
// picks it back up instead of losing it.
const STORAGE_KEY = "activeInvestigationId";

function readStoredId(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeId(id: string | null) {
  try {
    if (id) sessionStorage.setItem(STORAGE_KEY, id);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable (private mode etc.): refresh just won't resume.
  }
}

// Starts a background investigation and polls its status every second until
// it finishes. The backend saves the result to history itself.
export function useInvestigate(options?: { onComplete?: () => void }) {
  const [investigationId, setInvestigationId] = useState<string | null>(null);

  // Resume a stored investigation after a refresh (client-only, post-mount).
  useEffect(() => {
    setInvestigationId(readStoredId());
  }, []);

  const startMutation = useMutation({
    mutationFn: (context?: string | null) => startInvestigation(context),
    onSuccess: (id) => {
      storeId(id);
      setInvestigationId(id);
    },
  });

  const statusQuery = useQuery({
    queryKey: ["investigation", investigationId],
    queryFn: () => getInvestigation(investigationId!),
    enabled: investigationId !== null,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data === null || data?.running === false ? false : 1000;
    },
    // Keep polling if the user switches tabs during a long investigation.
    refetchIntervalInBackground: true,
    retry: 2,
  });

  // undefined while loading; null when the backend no longer has it.
  const status = statusQuery.data;
  const watching = investigationId !== null && status !== null;
  const running =
    startMutation.isPending || (watching && !statusQuery.isError && status?.running !== false);

  // Fire onComplete once when an investigation we were watching finishes.
  const onComplete = options?.onComplete;
  const completedId = useRef<string | null>(null);
  useEffect(() => {
    if (status && !status.running && completedId.current !== status.investigation_id) {
      completedId.current = status.investigation_id;
      onComplete?.();
    }
  }, [status, onComplete]);

  // The backend forgot it (expired or restarted): stop watching it.
  useEffect(() => {
    if (status === null) storeId(null);
  }, [status]);

  return {
    start: (context?: string | null) => startMutation.mutate(context),
    running,
    steps: status?.steps ?? [],
    result: status?.running === false ? status.result : null,
    error: startMutation.error ?? statusQuery.error,
  };
}
