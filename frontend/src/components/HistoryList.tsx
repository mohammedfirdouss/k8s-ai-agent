"use client";

import { useCallback, useEffect, useState } from "react";
import { insforge, insforgeConfigured } from "@/services/insforge";
import type { InvestigationRow } from "@/types";

type HistoryListProps = {
  // Bump this value to trigger a refetch (e.g. after an investigation).
  refreshKey: number;
};

async function fetchInvestigations(): Promise<InvestigationRow[]> {
  if (!insforge) return [];
  try {
    // Preferred: server-side ordering + limit (PostgREST-style chain).
    const { data, error } = await insforge.database
      .from("investigations")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(10);
    if (error) throw error;
    return (data ?? []) as InvestigationRow[];
  } catch {
    // Fallback: plain select, sort and trim client-side.
    try {
      const { data } = await insforge.database
        .from("investigations")
        .select("*");
      const rows = (data ?? []) as InvestigationRow[];
      return rows
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        )
        .slice(0, 10);
    } catch {
      return [];
    }
  }
}

export default function HistoryList({ refreshKey }: HistoryListProps) {
  const [rows, setRows] = useState<InvestigationRow[]>([]);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    const result = await fetchInvestigations();
    setRows(result);
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (!insforgeConfigured) return;
    void refresh();
  }, [refresh, refreshKey]);

  // Best-effort realtime: refresh the list when a new row is inserted.
  useEffect(() => {
    if (!insforgeConfigured || !insforge) return;
    let active = true;
    (async () => {
      try {
        await insforge.realtime.subscribe("investigations");
        insforge.realtime.on("INSERT", () => {
          if (active) void refresh();
        });
      } catch {
        // Realtime is optional; polling via refreshKey still works.
      }
    })();
    return () => {
      active = false;
      try {
        insforge?.realtime.unsubscribe("investigations");
      } catch {
        // Ignore teardown errors.
      }
    };
  }, [refresh]);

  if (!insforgeConfigured) return null;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="text-sm font-semibold text-slate-900">
        Recent Investigations
      </h2>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          {loaded ? "No investigations yet." : "Loading history..."}
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-4 font-semibold">Date</th>
                <th className="py-2 pr-4 font-semibold">Root Cause</th>
                <th className="py-2 pr-4 font-semibold">Confidence</th>
                <th className="py-2 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-slate-100">
                  <td className="whitespace-nowrap py-2 pr-4 text-slate-600">
                    {new Date(row.created_at).toLocaleString()}
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
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
