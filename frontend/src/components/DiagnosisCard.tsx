import type { Diagnosis, LLMUsage } from "@/types";
import AgentChecks from "@/components/ui/AgentChecks";
import IncidentCard from "@/components/ui/IncidentCard";

type DiagnosisCardProps = {
  diagnosis: Diagnosis;
};

function UsageFooter({ usage }: { usage: LLMUsage | null | undefined }) {
  if (!usage?.calls) return null;
  const tokens = usage.prompt_tokens + usage.completion_tokens;
  const parts = [
    `${usage.calls} AI ${usage.calls === 1 ? "call" : "calls"}`,
    `${tokens.toLocaleString()} tokens`,
    usage.cost_usd !== null ? `$${usage.cost_usd.toFixed(4)}` : null,
    `${usage.seconds.toFixed(1)}s`,
  ].filter(Boolean);
  return <p className="text-right text-[11.5px] text-ink-3 tabular-nums">{parts.join(" · ")}</p>;
}

export default function DiagnosisCard({ diagnosis }: DiagnosisCardProps) {
  if (diagnosis.error) {
    return (
      <section className="rounded-card bg-orange-tint p-4 shadow-card">
        <h2 className="text-[13px] font-semibold text-ink">AI analysis failed</h2>
        <p className="mt-1.5 text-[13px] leading-relaxed whitespace-pre-wrap text-ink-2">{diagnosis.error}</p>
      </section>
    );
  }

  if (diagnosis.incidents.length === 0) {
    return (
      <section className="rounded-card bg-green-tint p-4 shadow-card">
        <div className="flex items-start justify-between gap-4">
          <h2 className="text-[13px] font-semibold text-ink">No critical Kubernetes issues detected.</h2>
          {diagnosis.confidence !== null && (
            <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 text-[11.5px] font-medium text-green shadow-hairline tabular-nums">
              {Math.round(diagnosis.confidence)}% confidence
            </span>
          )}
        </div>
        <p className="mt-1.5 text-[13px] text-ink-2">{diagnosis.summary ?? "Cluster appears healthy."}</p>
      </section>
    );
  }

  const count = diagnosis.incidents.length;
  return (
    <div className="flex flex-col gap-3">
      <div className="px-0.5">
        <h2 className="text-[14px] font-semibold text-ink">
          {count} {count === 1 ? "issue" : "issues"} found
        </h2>
        {diagnosis.summary && <p className="mt-0.5 text-[13px] text-ink-2">{diagnosis.summary}</p>}
      </div>
      {diagnosis.incidents.map((incident, i) => (
        <IncidentCard key={i} incident={incident} index={i} />
      ))}
      <AgentChecks commands={diagnosis.commands_run} />
      <UsageFooter usage={diagnosis.usage} />
    </div>
  );
}
