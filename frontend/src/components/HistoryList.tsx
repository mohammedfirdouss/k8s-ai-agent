"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import DiagnosisCard from "@/components/DiagnosisCard";
import FeedbackPrompt from "@/components/FeedbackPrompt";
import { insforge, insforgeConfigured } from "@/services/insforge";
import type { Diagnosis, InvestigationRow } from "@/types";

type HistoryListProps = {
  // Signed-in user; history and its realtime channel are per user.
  userId: string | null;
  // Bump this value to trigger a refetch (e.g. after an investigation).
  refreshKey: number;
};

const HISTORY_COLUMNS = "id, created_at, root_cause, cluster_context, confidence, status";

async function fetchInvestigations(): Promise<InvestigationRow[]> {
  if (!insforge) return [];
  // RLS returns only the signed-in user's rows.
  const { data, error } = await insforge.database
    .from("investigations")
    .select(HISTORY_COLUMNS)
    .order("created_at", { ascending: false })
    .limit(10);
  if (error) throw error;
  return (data ?? []) as InvestigationRow[];
}

// Loads one saved diagnosis (the list query leaves this large column out).
type SavedRow = { diagnosis: Diagnosis | null; feedback: "helpful" | "not_helpful" | null };

async function fetchDiagnosis(id: string): Promise<SavedRow> {
  if (!insforge) return { diagnosis: null, feedback: null };
  const { data, error } = await insforge.database
    .from("investigations")
    .select("diagnosis, feedback")
    .eq("id", id)
    .limit(1);
  if (error) throw error;
  const row = data?.[0] as { diagnosis?: Partial<Diagnosis>; feedback?: SavedRow["feedback"] } | undefined;
  return { diagnosis: normalize(row?.diagnosis), feedback: row?.feedback ?? null };
}

function normalize(stored: Partial<Diagnosis> | undefined): Diagnosis | null {
  if (!stored) return null;
  // Normalize rows saved by older versions with fewer fields.
  return {
    summary: stored.summary ?? null,
    incidents: stored.incidents ?? [],
    root_cause: stored.root_cause ?? null,
    confidence: stored.confidence ?? null,
    error: stored.error ?? null,
    commands_run: stored.commands_run ?? [],
    usage: stored.usage ?? null,
  };
}

function SavedDiagnosis({ id }: { id: string }) {
  const [state, setState] = useState<
    { status: "loading" } | { status: "error" } | ({ status: "loaded" } & SavedRow)
  >({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchDiagnosis(id)
      .then((row) => !cancelled && setState({ status: "loaded", ...row }))
      .catch(() => !cancelled && setState({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (state.status === "loading") {
    return <p className="text-sm text-slate-500">Loading diagnosis...</p>;
  }
  if (state.status === "error") {
    return <p className="text-sm text-red-700">Could not load this diagnosis.</p>;
  }
  if (!state.diagnosis) {
    return <p className="text-sm text-slate-500">No details were saved for this investigation.</p>;
  }
  return (
    <div className="space-y-4">
      <DiagnosisCard diagnosis={state.diagnosis} />
      {!state.diagnosis.error && <FeedbackPrompt investigationId={id} initial={state.feedback} />}
    </div>
  );
}

export default function HistoryList({ userId, refreshKey }: HistoryListProps) {
  const [rows, setRows] = useState<InvestigationRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRows(await fetchInvestigations());
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (!insforgeConfigured || !userId) return;
    void refresh();
  }, [refresh, refreshKey, userId]);

  // Best-effort realtime: refresh the list when a new row is inserted on
  // this user's channel.
  useEffect(() => {
    if (!insforgeConfigured || !insforge || !userId) return;
    const channel = `investigations:${userId}`;
    const onInsert = () => void refresh();
    (async () => {
      try {
        await insforge.realtime.subscribe(channel);
        insforge.realtime.on("INSERT", onInsert);
      } catch {
        // Realtime is optional; refreshKey still refreshes after each run.
      }
    })();
    return () => {
      try {
        insforge?.realtime.off("INSERT", onInsert);
        insforge?.realtime.unsubscribe(channel);
      } catch {
        // Ignore teardown errors.
      }
    };
  }, [refresh, userId]);

  if (!insforgeConfigured) return null;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="text-sm font-semibold text-slate-900">
        Recent Investigations
      </h2>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          {!loaded
            ? "Loading history..."
            : loadError
              ? "Could not load history."
              : "No investigations yet."}
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-4 font-semibold">Date</th>
                <th className="py-2 pr-4 font-semibold">Cluster</th>
                <th className="py-2 pr-4 font-semibold">Root Cause</th>
                <th className="py-2 pr-4 font-semibold">Confidence</th>
                <th className="py-2 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Fragment key={row.id}>
                <tr
                  onClick={() => setExpandedId(expandedId === row.id ? null : row.id)}
                  aria-expanded={expandedId === row.id}
                  className="cursor-pointer border-b border-slate-100 hover:bg-slate-50"
                >
                  <td className="whitespace-nowrap py-2 pr-4 text-slate-600">
                    {new Date(row.created_at).toLocaleString()}
                  </td>
                  <td className="whitespace-nowrap py-2 pr-4 text-slate-600">
                    {row.cluster_context ?? "default"}
                  </td>
                  <td className="max-w-md truncate py-2 pr-4 text-slate-800">
                    {row.root_cause ?? "—"}
                  </td>
                  <td className="py-2 pr-4 text-slate-600">
                    {row.confidence !== null && row.confidence !== undefined
                      ? `${Math.round(Number(row.confidence))}%`
                      : "—"}
                  </td>
                  <td className="py-2">
                    <span
                      className={
                        row.status === "completed"
                          ? "rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700"
                          : "rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700"
                      }
                    >
                      {row.status ?? "unknown"}
                    </span>
                  </td>
                </tr>
                {expandedId === row.id && (
                  <tr className="border-b border-slate-100">
                    <td colSpan={5} className="bg-slate-50 p-4">
                      <SavedDiagnosis id={row.id} />
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
