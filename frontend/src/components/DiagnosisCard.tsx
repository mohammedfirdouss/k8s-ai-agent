"use client";

import { useState } from "react";
import type { Diagnosis, Incident, Severity } from "@/types";

type DiagnosisCardProps = {
  diagnosis: Diagnosis;
};

const SEVERITY_STYLES: Record<Severity, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-700",
};

function Field({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </h4>
      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{value}</p>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // Clipboard unavailable (e.g. insecure context); ignore.
        }
      }}
      className="shrink-0 rounded border border-slate-600 px-2 py-0.5 text-[11px] text-slate-300 transition-colors hover:bg-slate-700"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function IncidentCard({ incident, index }: { incident: Incident; index: number }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${SEVERITY_STYLES[incident.severity]}`}
            >
              {incident.severity}
            </span>
            {incident.workload && (
              <span className="font-mono text-xs text-slate-600">
                {incident.namespace ? `${incident.namespace}/` : ""}
                {incident.workload}
              </span>
            )}
          </div>
          <h3 className="mt-2 text-sm font-semibold text-slate-900">
            {index + 1}. {incident.root_cause}
          </h3>
        </div>
        {incident.confidence !== null && (
          <span className="shrink-0 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
            Confidence: {Math.round(incident.confidence)}%
          </span>
        )}
      </div>

      <div className="mt-4 space-y-4">
        <Field label="Explanation" value={incident.explanation} />

        {incident.evidence.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Evidence
            </h4>
            <ul className="mt-1 space-y-1">
              {incident.evidence.map((line, i) => (
                <li
                  key={i}
                  className="break-words rounded bg-slate-50 px-2 py-1 font-mono text-xs text-slate-700"
                >
                  {line}
                </li>
              ))}
            </ul>
          </div>
        )}

        <Field label="Suggested Fix" value={incident.fix} />

        {incident.kubectl_commands.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              kubectl Commands
            </h4>
            <ul className="mt-1 space-y-1 rounded-md bg-slate-900 p-3">
              {incident.kubectl_commands.map((command, i) => (
                <li key={i} className="flex items-start justify-between gap-3">
                  <code className="overflow-x-auto whitespace-pre text-xs leading-6 text-slate-100">
                    {command}
                  </code>
                  <CopyButton text={command} />
                </li>
              ))}
            </ul>
          </div>
        )}

        <Field label="Prevention" value={incident.prevention} />

        {incident.confidence_reasoning && (
          <p className="text-xs text-slate-500">{incident.confidence_reasoning}</p>
        )}
      </div>
    </section>
  );
}

// Read-only checks the agent ran beyond the standard evidence collection.
function CommandsRun({ commands }: { commands: string[] }) {
  if (!commands?.length) return null;
  return (
    <details className="rounded-lg border border-slate-200 bg-white px-5 py-3 text-sm">
      <summary className="cursor-pointer text-slate-700">
        The agent ran {commands.length} extra read-only{" "}
        {commands.length === 1 ? "check" : "checks"}
      </summary>
      <ul className="mt-2 space-y-1">
        {commands.map((command, i) => (
          <li key={i} className="font-mono text-xs text-slate-600">
            {command}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function DiagnosisCard({ diagnosis }: DiagnosisCardProps) {
  if (diagnosis.error) {
    return (
      <section className="rounded-lg border border-amber-300 bg-amber-50 p-5">
        <h2 className="text-sm font-semibold text-amber-900">
          AI analysis failed
        </h2>
        <p className="mt-2 whitespace-pre-wrap text-sm text-amber-800">
          {diagnosis.error}
        </p>
      </section>
    );
  }

  if (diagnosis.incidents.length === 0) {
    return (
      <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-5">
        <div className="flex items-start justify-between gap-4">
          <h2 className="text-sm font-semibold text-emerald-900">
            No critical Kubernetes issues detected.
          </h2>
          {diagnosis.confidence !== null && (
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-800">
              Confidence: {Math.round(diagnosis.confidence)}%
            </span>
          )}
        </div>
        <p className="mt-2 text-sm text-emerald-800">
          {diagnosis.summary ?? "Cluster appears healthy."}
        </p>
      </section>
    );
  }

  const count = diagnosis.incidents.length;
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-900">
          Diagnosis — {count} {count === 1 ? "issue" : "issues"} found
        </h2>
        {diagnosis.summary && (
          <p className="mt-1 text-sm text-slate-600">{diagnosis.summary}</p>
        )}
      </div>
      {diagnosis.incidents.map((incident, i) => (
        <IncidentCard key={i} incident={incident} index={i} />
      ))}
      <CommandsRun commands={diagnosis.commands_run} />
    </div>
  );
}
