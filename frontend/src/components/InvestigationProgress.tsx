import type { ProgressStep } from "@/types";

type InvestigationProgressProps = {
  steps: ProgressStep[];
};

function StepIndicator({ status }: { status: ProgressStep["status"] }) {
  if (status === "done") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-xs font-semibold text-emerald-700">
        ✓
      </span>
    );
  }
  if (status === "running") {
    return (
      <span className="flex h-5 w-5 items-center justify-center">
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
      </span>
    );
  }
  return (
    <span className="flex h-5 w-5 items-center justify-center">
      <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
    </span>
  );
}

export default function InvestigationProgress({
  steps,
}: InvestigationProgressProps) {
  if (steps.length === 0) return null;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="text-sm font-semibold text-slate-900">
        Investigation Progress
      </h2>
      <ul className="mt-4 space-y-3">
        {steps.map((step) => (
          <li key={step.name} className="flex items-center gap-3">
            <StepIndicator status={step.status} />
            <span
              className={
                step.status === "pending"
                  ? "text-sm text-slate-400"
                  : step.status === "running"
                    ? "text-sm font-medium text-slate-900"
                    : "text-sm text-slate-700"
              }
            >
              {step.name}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
