"use client";

// Adapted from Beautiful UI's FilterTable (MIT, see LICENSE-beautiful-ui.txt):
// status chips filter the table in place; here rows are buttons that
// expand to the saved diagnosis.

import { useState, type ReactNode } from "react";
import type { InvestigationRow } from "@/types";

type Filter = "all" | "completed" | "failed";

// Phones show date, root cause and status; wider screens add cluster and confidence.
const COLUMNS =
  "grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)_auto] sm:grid-cols-[minmax(0,0.95fr)_minmax(0,0.8fr)_minmax(0,1.9fr)_minmax(0,0.65fr)_minmax(0,0.7fr)]";
const WIDE_ONLY = "hidden sm:block";

function isFailed(row: InvestigationRow) {
  return row.status !== "completed";
}

function ConfidenceCell({ value }: { value: number | null }) {
  if (value === null || value === undefined) return <span className="text-ink-3">—</span>;
  const n = Math.round(Number(value));
  const tone = n >= 80 ? "var(--green)" : n >= 50 ? "var(--orange)" : "var(--ink-3)";
  const signal = n >= 80 ? 3 : n >= 50 ? 2 : 1;
  return (
    <span className="flex items-center gap-1.5">
      <span className="flex items-end gap-0.5" aria-hidden>
        {[0, 1, 2].map((bar) => (
          <span key={bar} className="w-1 rounded-full" style={{ height: 6 + bar * 2, background: bar < signal ? tone : "var(--line-strong)" }} />
        ))}
      </span>
      <span className="tabular-nums">{n}%</span>
    </span>
  );
}

export default function HistoryTable({
  rows,
  expandedId,
  onToggle,
  renderExpanded,
}: {
  rows: InvestigationRow[];
  expandedId: string | null;
  onToggle: (id: string) => void;
  renderExpanded: (id: string) => ReactNode;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const failedCount = rows.filter(isFailed).length;
  const filters: { key: Filter; label: string; dot?: string; count: number }[] = [
    { key: "all", label: "All", count: rows.length },
    { key: "completed", label: "Completed", dot: "var(--green)", count: rows.length - failedCount },
    { key: "failed", label: "Failed", dot: "var(--red)", count: failedCount },
  ];
  const visible = rows.filter(
    (row) => filter === "all" || (filter === "failed" ? isFailed(row) : !isFailed(row)),
  );

  return (
    <div className="w-full">
      <div className="-mx-1 mb-1.5 flex items-center gap-1 overflow-x-auto px-1 py-1" role="group" aria-label="Filter by status">
        {filters.map((f) => {
          const active = filter === f.key;
          return (
            <button
              key={f.key}
              type="button"
              aria-pressed={active}
              onClick={() => setFilter(f.key)}
              className={`flex h-[26px] shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium
                transition-[background-color,box-shadow,color] duration-200
                ${active ? "bg-surface text-ink shadow-btn" : "text-ink-2 hover:bg-hover"}`}
            >
              {f.dot && <span className="size-1.5 rounded-full" style={{ background: f.dot }} aria-hidden />}
              {f.label}
              <span className={`rounded-[4px] px-1 text-[10.5px] tabular-nums ${active ? "bg-field text-ink-2" : "text-ink-3"}`}>
                {f.count}
              </span>
            </button>
          );
        })}
      </div>

      <div className="overflow-hidden rounded-card bg-surface shadow-card" role="region" aria-label="Investigation history">
        <div>
          <div className={`grid ${COLUMNS} border-b border-[var(--grid-line)] text-[12px] font-medium text-ink-2`}>
            <span className="border-r border-[var(--grid-line)] px-3 py-2">Date</span>
            <span className={`border-r border-[var(--grid-line)] px-3 py-2 ${WIDE_ONLY}`}>Cluster</span>
            <span className="border-r border-[var(--grid-line)] px-3 py-2">Root cause</span>
            <span className={`border-r border-[var(--grid-line)] px-3 py-2 ${WIDE_ONLY}`}>Confidence</span>
            <span className="px-3 py-2">Status</span>
          </div>

          {visible.length === 0 && (
            <p className="px-3 py-4 text-[12.5px] text-ink-3">No {filter} investigations.</p>
          )}

          {visible.map((row) => {
            const expanded = expandedId === row.id;
            const failed = isFailed(row);
            return (
              <div key={row.id} className="border-b border-[var(--grid-line)] last:border-b-0">
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => onToggle(row.id)}
                  className={`grid w-full ${COLUMNS} text-left text-[12.5px] transition-colors duration-100
                    hover:bg-hover ${expanded ? "bg-hover" : ""}`}
                >
                  <span className="truncate border-r border-[var(--grid-line)] px-3 py-2 text-ink-2 tabular-nums">
                    {new Date(row.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                  </span>
                  <span className={`truncate border-r border-[var(--grid-line)] px-3 py-2 font-mono text-[11.5px] text-ink-2 ${WIDE_ONLY}`}>
                    {row.cluster_context ?? "default"}
                  </span>
                  <span className="truncate border-r border-[var(--grid-line)] px-3 py-2 font-medium text-ink" title={row.root_cause ?? undefined}>
                    {row.root_cause ?? "—"}
                  </span>
                  <span className={`border-r border-[var(--grid-line)] px-3 py-2 text-ink-2 ${WIDE_ONLY}`}>
                    <ConfidenceCell value={row.confidence} />
                  </span>
                  <span className="px-3 py-2">
                    <span className={`inline-flex h-[22px] items-center rounded-[8px] px-[7px] text-[12px] font-medium ${failed ? "status-tag-failed" : "status-tag-done"}`}>
                      {failed ? (row.status ?? "unknown") : "completed"}
                    </span>
                  </span>
                </button>
                {expanded && <div className="border-t border-[var(--grid-line)] bg-inset p-3">{renderExpanded(row.id)}</div>}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
