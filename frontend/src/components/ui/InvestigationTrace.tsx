"use client";

// Adapted from Beautiful UI's ThinkingState (MIT, see LICENSE-beautiful-ui.txt).
// Driven by the backend's real step progress instead of a timed demo: a
// shimmering header while running, a spinner on the active step, checks with
// each step's finding once done, and a collapsible trace.

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ProgressStep } from "@/types";

function useElapsedSeconds(running: boolean): number | null {
  const startedAt = useRef<number | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);
  useEffect(() => {
    if (!running) return;
    startedAt.current ??= Date.now();
    const tick = () => setElapsed(Math.round((Date.now() - startedAt.current!) / 1000));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [running]);
  return elapsed;
}

function StepIcon({ status }: { status: ProgressStep["status"] }) {
  if (status === "running") {
    return (
      <span
        className="size-3 shrink-0 rounded-full border-[1.5px] border-line-strong border-t-ink-2"
        style={{ animation: "spin 700ms linear infinite" }}
        aria-hidden
      />
    );
  }
  if (status === "done") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="2.5"
        strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-hidden>
        <path d="M20 6L9 17l-5-5" />
      </svg>
    );
  }
  return <span className="mx-[3px] size-2 shrink-0 rounded-full bg-line-strong" aria-hidden />;
}

export default function InvestigationTrace({
  steps,
  running,
}: {
  steps: ProgressStep[];
  running: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const elapsed = useElapsedSeconds(running);
  const doneCount = steps.filter((s) => s.status === "done").length;

  const traceRef = useRef<HTMLDivElement>(null);
  const [lineHeight, setLineHeight] = useState(0);
  useLayoutEffect(() => {
    if (traceRef.current) setLineHeight(traceRef.current.offsetHeight);
  }, [steps, expanded]);

  const header = running
    ? `Investigating${elapsed ? ` · ${elapsed}s` : ""}`
    : `Investigation complete${elapsed ? ` in ${elapsed}s` : ""}`;

  return (
    <section className="rounded-card bg-surface px-4 py-3 shadow-card" aria-label="Investigation progress">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((open) => !open)}
        className="-mx-1.5 flex w-full items-center gap-2 rounded-control px-1.5 py-1 text-left
          transition-colors duration-100 hover:bg-hover-2"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill={running ? "var(--ink-2)" : "var(--ink-3)"} aria-hidden>
          <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z" />
        </svg>
        <span role="status" className="min-w-0 flex-1">
          {running ? (
            <span
              className="bg-clip-text text-[13px] font-medium whitespace-nowrap text-transparent"
              style={{
                backgroundImage: "linear-gradient(90deg, var(--ink-3) 35%, var(--ink) 50%, var(--ink-3) 65%)",
                backgroundSize: "200% 100%",
                animation: "shimmer-text 1.4s linear infinite",
              }}
            >
              {header}
            </span>
          ) : (
            <span className="text-[13px] font-medium text-ink-2" style={{ animation: "fade-in 350ms ease-out both" }}>
              {header}
            </span>
          )}
        </span>
        <span className="shrink-0 text-[11.5px] text-ink-3 tabular-nums">
          {doneCount}/{steps.length}
        </span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ink-3)" strokeWidth="2.2"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden
          className="shrink-0 transition-transform duration-300"
          style={{ transform: expanded ? "rotate(180deg)" : "rotate(0)" }}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      <div
        className="grid transition-[grid-template-rows,opacity] duration-400"
        style={{
          gridTemplateRows: expanded ? "1fr" : "0fr",
          opacity: expanded ? 1 : 0,
          transitionTimingFunction: "var(--ease-out-strong)",
        }}
      >
        <div className="overflow-hidden">
          <div className="relative mt-1 ml-[5px] pl-4">
            <span
              aria-hidden
              className="absolute left-[3px] w-px bg-line"
              style={{ top: -6, height: lineHeight ? lineHeight - 4 : 0, transition: "height 500ms var(--ease-out-strong)" }}
            />
            <ol ref={traceRef} className="flex flex-col gap-0.5 py-1">
              {steps.map((step) => (
                <li
                  key={step.name}
                  className="flex min-h-7 items-center gap-2 rounded-[6px] px-1.5 py-0.5"
                  style={{ animation: "fade-up 320ms var(--ease-out-strong) both" }}
                >
                  <span className="flex w-3.5 shrink-0 justify-center">
                    <StepIcon status={step.status} />
                  </span>
                  <span
                    className={`shrink-0 text-[12.5px] ${
                      step.status === "pending" ? "text-ink-3" : "font-medium text-ink"
                    }`}
                  >
                    {step.name}
                  </span>
                  {step.detail && (
                    <span className="min-w-0 truncate text-[11.5px] text-ink-2" title={step.detail}>
                      {step.detail}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </section>
  );
}
