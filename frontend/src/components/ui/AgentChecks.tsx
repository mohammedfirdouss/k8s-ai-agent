"use client";

// Adapted from Beautiful UI's ToolChips (MIT, see LICENSE-beautiful-ui.txt):
// the read-only kubectl checks the agent chose to run, as compact rows with
// a target chip; each row expands to the exact command.

import { useState } from "react";

type Check = { label: string; target: string; icon: "read" | "list"; command: string };

const ICONS = {
  read: (
    <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </g>
  ),
  list: (
    <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 6h16M4 12h16M4 18h10" />
    </g>
  ),
};

function plural(kind: string): string {
  if (kind.endsWith("s")) return kind === "ingress" ? "ingresses" : kind; // e.g. endpoints
  if (kind.endsWith("y")) return `${kind.slice(0, -1)}ies`; // networkpolicy -> networkpolicies
  return `${kind}s`;
}

// Commands come from the backend's fixed tool menu (app/ai/tools.py).
function describe(command: string): Check {
  const args = command.replace(/^kubectl\s+/, "").split(/\s+/);
  const flag = (name: string) => {
    const at = args.indexOf(name);
    return at >= 0 ? args[at + 1] : undefined;
  };
  const namespace = flag("-n");
  const where = (target: string) => (namespace ? `${target} · ${namespace}` : target);
  const [verb, first, second] = args;

  if (verb === "logs") {
    return { label: args.includes("--previous") ? "Read previous logs" : "Read logs", target: where(`pod/${first}`), icon: "read", command };
  }
  if (verb === "describe") return { label: "Describe", target: where(`${first}/${second}`), icon: "read", command };
  if (verb === "get" && flag("-o") === "yaml") return { label: "Read YAML", target: where(`${first}/${second}`), icon: "read", command };
  if (verb === "get") return { label: "List", target: where(plural(first)), icon: "list", command };
  return { label: "Run", target: command, icon: "list", command };
}

export default function AgentChecks({ commands }: { commands: string[] }) {
  const [open, setOpen] = useState(false);
  const [openRows, setOpenRows] = useState<Set<number>>(new Set());
  if (commands.length === 0) return null;
  const checks = commands.map(describe);

  const toggleRow = (index: number) =>
    setOpenRows((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  return (
    <div className="w-full rounded-card bg-surface px-3 py-2 shadow-card">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="-mx-1.5 flex w-fit items-center gap-1.5 rounded-control px-1.5 py-1 text-[12.5px] text-ink-2
          transition-colors duration-100 hover:bg-hover-2"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden
          className="transition-transform duration-200" style={{ transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}>
          <path d="M6 9l6 6 6-6" />
        </svg>
        <span className="tabular-nums">
          The agent ran {checks.length} read-only {checks.length === 1 ? "check" : "checks"}
        </span>
      </button>

      <div
        className="grid transition-[grid-template-rows,opacity] duration-300"
        style={{ gridTemplateRows: open ? "1fr" : "0fr", opacity: open ? 1 : 0 }}
        inert={!open}
      >
        <div className="-mx-1 overflow-hidden px-1.5 pb-1">
          <ul className="mt-1.5 flex flex-col gap-1">
            {checks.map((check, i) => {
              const rowOpen = openRows.has(i);
              return (
                <li key={i}>
                  <button
                    type="button"
                    aria-expanded={rowOpen}
                    onClick={() => toggleRow(i)}
                    className="group/row -mx-[3px] flex h-7 w-[calc(100%+6px)] min-w-0 items-center gap-2 rounded-control px-[3px]
                      text-left transition-colors duration-100 hover:bg-hover-2"
                  >
                    <span className="relative flex size-4 shrink-0 items-center justify-center text-ink-3">
                      <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden
                        className={`transition-opacity duration-100 group-hover/row:opacity-0 ${rowOpen ? "opacity-0" : ""}`}>
                        {ICONS[check.icon]}
                      </svg>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
                        strokeLinecap="round" strokeLinejoin="round" aria-hidden
                        className={`absolute transition-[opacity,transform] duration-150 group-hover/row:opacity-100 ${rowOpen ? "opacity-100" : "opacity-0"}`}
                        style={{ transform: rowOpen ? "rotate(0deg)" : "rotate(-90deg)" }}>
                        <path d="M6 9l6 6 6-6" />
                      </svg>
                    </span>
                    <span className="shrink-0 text-[12.5px] font-medium text-ink">{check.label}</span>
                    <span className="inline-flex h-5.5 min-w-0 flex-1 items-center truncate rounded-chip bg-field px-1.5 font-mono text-[11.5px] text-ink-2 shadow-hairline">
                      {check.target}
                    </span>
                  </button>
                  <div
                    className="grid transition-[grid-template-rows,opacity] duration-300"
                    style={{ gridTemplateRows: rowOpen ? "1fr" : "0fr", opacity: rowOpen ? 1 : 0 }}
                  >
                    <div className="min-h-0 overflow-hidden">
                      <p className="mt-0.5 mb-1 ml-2 border-l border-line py-0.5 pl-3.5 font-mono text-[11.5px] leading-[1.6] break-all text-ink-2">
                        {check.command}
                      </p>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
