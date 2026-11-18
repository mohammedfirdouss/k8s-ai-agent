"use client";

// Adapted from Beautiful UI's RecommendationCard (MIT, see LICENSE-beautiful-ui.txt):
// the card holds its shape; "Details" opens a drawer as a distinct section
// (evidence, commands, prevention) and the footer carries a 3-bar
// confidence meter with the primary action.

import { useState } from "react";
import type { Incident, Severity } from "@/types";
import { Button } from "@/components/ui/Button";
import CommandBlock from "@/components/ui/CommandBlock";
import EvidenceCards from "@/components/ui/EvidenceCards";

const SEVERITY: Record<Severity, { cls: string; ring: string }> = {
  critical: { cls: "bg-red-tint text-red", ring: "0 0 0 1px color-mix(in oklch, var(--red) 28%, transparent)" },
  high: { cls: "bg-orange-tint text-orange", ring: "0 0 0 1px color-mix(in oklch, var(--orange) 28%, transparent)" },
  medium: { cls: "bg-accent-tint text-accent-ink", ring: "0 0 0 1px color-mix(in oklch, var(--accent) 28%, transparent)" },
  low: { cls: "bg-field text-ink-2", ring: "var(--shadow-hairline)" },
};

function confidenceLevel(confidence: number | null) {
  if (confidence === null) return { signal: 0, tone: "var(--ink-3)", label: "Confidence unknown" };
  const pct = `${Math.round(confidence)}%`;
  if (confidence >= 80) return { signal: 3, tone: "var(--green)", label: `High confidence · ${pct}` };
  if (confidence >= 50) return { signal: 2, tone: "var(--orange)", label: `Medium confidence · ${pct}` };
  return { signal: 1, tone: "var(--ink-3)", label: `Low confidence · ${pct}, cause unclear` };
}

function Meter({ signal, tone }: { signal: number; tone: string }) {
  return (
    <span className="flex items-end gap-0.5" aria-hidden>
      {[0, 1, 2].map((bar) => (
        <span
          key={bar}
          className="w-1 rounded-full transition-colors duration-300"
          style={{ height: 6 + bar * 2, background: bar < signal ? tone : "var(--line-strong)" }}
        />
      ))}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-1 px-0.5 text-[12px] font-semibold text-ink">{title}</h4>
      {children}
    </div>
  );
}

export default function IncidentCard({ incident, index }: { incident: Incident; index: number }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const level = confidenceLevel(incident.confidence);
  const severity = SEVERITY[incident.severity] ?? SEVERITY.medium;
  const fixCommand = incident.kubectl_commands[0];
  const where = [incident.namespace, incident.workload].filter(Boolean).join("/");

  function copyFix() {
    if (!fixCommand) return;
    navigator.clipboard
      .writeText(fixCommand)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => {
        // Clipboard unavailable (e.g. insecure context): nothing to do.
      });
  }

  return (
    <article
      className="w-full overflow-hidden rounded-card bg-surface shadow-card"
      style={{ animation: `fade-up 400ms var(--ease-out-strong) ${index * 80}ms both` }}
    >
      <div className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center rounded-full px-1.5 text-[11.5px] font-medium capitalize ${severity.cls}`}
            style={{ boxShadow: severity.ring }}
          >
            {incident.severity}
          </span>
          {where && (
            <span className="inline-flex min-w-0 items-center rounded-full bg-field px-2 py-px font-mono text-[11.5px] text-ink-2 shadow-hairline">
              <span className="truncate">{where}</span>
            </span>
          )}
        </div>
        <h3 className="mt-2.5 text-[14px] leading-snug font-medium text-ink">{incident.root_cause}</h3>
        {incident.explanation && (
          <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">{incident.explanation}</p>
        )}
        {incident.fix && (
          <p className="mt-2.5 text-[13px] leading-relaxed text-ink-2">
            <span className="font-medium text-ink">Suggested fix: </span>
            {incident.fix}
          </p>
        )}
      </div>

      {/* details drawer: a distinct section of the card */}
      <div
        className="grid transition-[grid-template-rows,opacity] duration-300"
        style={{
          gridTemplateRows: open ? "1fr" : "0fr",
          opacity: open ? 1 : 0,
          transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)",
        }}
        inert={!open}
      >
        <div className="overflow-hidden">
          <div className="flex flex-col gap-4 border-t border-line bg-inset p-4">
            {incident.kubectl_commands.length > 0 && (
              <Section title="Commands">
                <CommandBlock lines={incident.kubectl_commands} />
              </Section>
            )}
            <EvidenceCards lines={incident.evidence} />
            {incident.prevention && (
              <Section title="Prevention">
                <p className="px-0.5 text-[13px] leading-relaxed text-ink-2">{incident.prevention}</p>
              </Section>
            )}
            {incident.confidence_reasoning && (
              <Section title="Why this confidence">
                <p className="px-0.5 text-[12.5px] leading-relaxed text-ink-2">{incident.confidence_reasoning}</p>
              </Section>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-2.5">
        <span className="flex items-center gap-2">
          <Meter signal={level.signal} tone={level.tone} />
          <span className="text-[12.5px] font-medium text-ink-2">{level.label}</span>
        </span>
        <span className="flex items-center gap-2">
          <Button variant="secondary" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
            {open ? "Hide details" : "Details"}
          </Button>
          {fixCommand && (
            <Button variant={copied ? "success" : "accent"} onClick={copyFix} title={fixCommand}>
              {copied ? "Copied" : "Copy fix"}
            </Button>
          )}
        </span>
      </div>
    </article>
  );
}
