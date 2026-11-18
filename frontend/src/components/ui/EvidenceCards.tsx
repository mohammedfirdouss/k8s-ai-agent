// Adapted from Beautiful UI's ContextCards (MIT, see LICENSE-beautiful-ui.txt):
// the quoted evidence an incident rests on, one card per line, each tagged
// with the kind of source it most likely came from.

type Source = { badge: string; label: string; tone: string };

// The model returns evidence as plain strings; tag them by what they quote.
function sourceOf(line: string): Source {
  const text = line.toLowerCase();
  if (/selector|labels?\b|endpoints?/.test(text)) return { badge: "SVC", label: "Service", tone: "bg-accent" };
  if (/probe|back-off|backoff|failed to|failedscheduling|insufficient|unhealthy|pulling image|not found/.test(text)) {
    return { badge: "EVT", label: "Event", tone: "bg-orange" };
  }
  if (/exit(ed)? (code|with)|exitcode|oomkilled|restart|limits?:|requests?:|status/.test(text)) {
    return { badge: "POD", label: "Pod status", tone: "bg-red" };
  }
  if (/error|fatal|exception|traceback|panic|warn|\[\w+\]/.test(text)) return { badge: "LOG", label: "Log", tone: "bg-green" };
  return { badge: "INF", label: "Observation", tone: "bg-ink-3" };
}

export default function EvidenceCards({ lines }: { lines: string[] }) {
  if (lines.length === 0) return null;
  return (
    <div className="flex w-full flex-col gap-2">
      <div className="flex items-center gap-2 px-0.5">
        <span className="text-[12px] font-semibold text-ink">Evidence</span>
        <span className="inline-flex h-5 items-center rounded-md bg-inset px-1.5 text-[11.5px] font-medium text-ink-2 shadow-hairline tabular-nums">
          {lines.length}
        </span>
      </div>
      <ul className="flex flex-col gap-1.5">
        {lines.map((line, i) => {
          const source = sourceOf(line);
          return (
            <li
              key={i}
              className="overflow-hidden rounded-card bg-surface shadow-card"
              style={{ animation: `fade-up 400ms var(--ease-out-strong) ${i * 60}ms both` }}
            >
              <p className="px-3 pt-2 pb-1 font-mono text-[12px] leading-relaxed break-words text-ink-2">{line}</p>
              <div className="px-3 pb-2">
                <span className="inline-flex h-5 items-center gap-1.5 rounded-full bg-inset px-1.5 text-[11px] font-medium text-ink-2 shadow-btn">
                  <span className={`flex h-3.5 min-w-3.5 items-center justify-center rounded-[4px] px-0.5 ${source.tone} text-[7px] font-bold text-white`}>
                    {source.badge}
                  </span>
                  {source.label}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
