type StatusBadgeProps = {
  label: string;
  tone: "ok" | "down" | "pending";
};

const TONES: Record<StatusBadgeProps["tone"], { badge: string; dot: string }> = {
  ok: { badge: "bg-emerald-50 text-emerald-700", dot: "bg-emerald-500" },
  down: { badge: "bg-red-50 text-red-700", dot: "bg-red-500" },
  pending: { badge: "bg-slate-100 text-slate-600", dot: "bg-slate-400" },
};

export default function StatusBadge({ label, tone }: StatusBadgeProps) {
  const style = TONES[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${style.badge}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {label}
    </span>
  );
}
