import type { Diagnosis } from "@/types";

type DiagnosisCardProps = {
  diagnosis: Diagnosis;
};

function Field({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </h3>
      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{value}</p>
    </div>
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

  // Backend healthy short-circuit: no critical issues were found.
  if (diagnosis.root_cause === "No problems detected") {
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
          Cluster appears healthy.
        </p>
      </section>
    );
  }

  const hasContent =
    diagnosis.root_cause ||
    diagnosis.explanation ||
    diagnosis.fix ||
    (diagnosis.kubectl_commands && diagnosis.kubectl_commands.length > 0) ||
    diagnosis.prevention ||
    diagnosis.confidence !== null;

  if (!hasContent) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-slate-900">Diagnosis</h2>
        <p className="mt-2 text-sm text-slate-500">
          The investigation completed but returned no diagnosis details.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-sm font-semibold text-slate-900">Diagnosis</h2>
        {diagnosis.confidence !== null && (
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
            Confidence: {Math.round(diagnosis.confidence)}%
          </span>
        )}
      </div>

      <div className="mt-4 space-y-5">
        <Field label="Root Cause" value={diagnosis.root_cause} />
        <Field label="Explanation" value={diagnosis.explanation} />
        <Field label="Suggested Fix" value={diagnosis.fix} />

        {diagnosis.kubectl_commands && diagnosis.kubectl_commands.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              kubectl Commands
            </h3>
            <pre className="mt-1 overflow-x-auto rounded-md bg-slate-900 p-3 text-xs leading-6 text-slate-100">
              {diagnosis.kubectl_commands.join("\n")}
            </pre>
          </div>
        )}

        <Field label="Prevention" value={diagnosis.prevention} />

        {diagnosis.confidence_reasoning && (
          <p className="text-xs text-slate-500">
            {diagnosis.confidence_reasoning}
          </p>
        )}
      </div>
    </section>
  );
}
