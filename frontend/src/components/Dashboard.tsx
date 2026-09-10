"use client";

import { useState } from "react";
import { useInvestigate } from "@/hooks/useInvestigate";
import { toErrorMessage } from "@/services/api";
import { insforge, insforgeConfigured } from "@/services/insforge";
import DiagnosisCard from "@/components/DiagnosisCard";
import HistoryList from "@/components/HistoryList";
import InvestigationProgress from "@/components/InvestigationProgress";

type DashboardProps = {
  email: string | null;
  onSignedOut: () => void;
};

export default function Dashboard({ email, onSignedOut }: DashboardProps) {
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const { mutation, progress } = useInvestigate({
    onComplete: () => setHistoryRefreshKey((k) => k + 1),
  });

  const running = mutation.isPending;
  const diagnosis = mutation.data?.diagnosis;

  async function handleSignOut() {
    try {
      await insforge?.auth.signOut();
    } catch {
      // Ignore sign-out errors; clear local state regardless.
    }
    onSignedOut();
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
          <h1 className="text-lg font-semibold tracking-tight text-slate-900">
            AI Kubernetes Agent
          </h1>
          {insforgeConfigured && (
            <div className="flex items-center gap-3">
              {email && <span className="text-sm text-slate-600">{email}</span>}
              <button
                type="button"
                onClick={handleSignOut}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition-colors hover:bg-slate-100"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>

      <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
        {!insforgeConfigured && (
          <p className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm text-slate-500">
            InsForge not configured — running without login and history
          </p>
        )}

        <div>
          <button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={running}
            className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {running && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-500 border-t-white" />
            )}
            {running ? "Investigating..." : "Investigate Cluster"}
          </button>
          <p className="mt-2 text-xs text-slate-500">
            Collects pod, log, event, deployment, and network data, then runs
            AI analysis. May take up to 2 minutes.
          </p>
        </div>

        {mutation.isError && (
          <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {toErrorMessage(mutation.error)}
          </p>
        )}

        {(running || mutation.isSuccess) && progress && (
          <InvestigationProgress
            steps={
              mutation.isSuccess
                ? progress.steps.map((s) => ({ ...s, status: "done" as const }))
                : progress.steps
            }
          />
        )}

        {diagnosis && <DiagnosisCard diagnosis={diagnosis} />}

        <HistoryList refreshKey={historyRefreshKey} />
      </div>
    </main>
  );
}
