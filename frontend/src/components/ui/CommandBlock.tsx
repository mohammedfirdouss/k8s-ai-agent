"use client";

// Adapted from Beautiful UI's CodeBlock (MIT, see LICENSE-beautiful-ui.txt):
// a light, line-numbered panel. Highlighting is tuned for kubectl/shell
// (command, flags, quoted values, <placeholders>), and every line has its
// own copy button next to copy-all.

import { useCallback, useState, type ReactNode } from "react";

const TOKEN = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|<[^>\s]+>|(?<=^|\s)--?[\w-]+(?:=\S*)?|^\s*\w[\w.-]*)/g;

function highlight(line: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of line.matchAll(TOKEN)) {
    const index = match.index ?? 0;
    const token = match[0];
    if (index > last) nodes.push(<span key={key++}>{line.slice(last, index)}</span>);
    let style: React.CSSProperties;
    if (token.startsWith("<")) style = { color: "var(--red)" }; // placeholder to fill in
    else if (/^["']/.test(token)) style = { color: "var(--orange)" }; // quoted value
    else if (token.trimStart().startsWith("-")) style = { color: "var(--ink-3)" }; // flag
    else style = { color: "var(--accent-ink)", fontWeight: 500 }; // the command itself
    nodes.push(<span key={key++} style={style}>{token}</span>);
    last = index + token.length;
  }
  if (last < line.length) nodes.push(<span key={key++}>{line.slice(last)}</span>);
  return nodes;
}

function useCopy(): [string | null, (text: string) => void] {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = useCallback((text: string) => {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(text);
        setTimeout(() => setCopied((current) => (current === text ? null : current)), 1500);
      })
      .catch(() => {
        // Clipboard unavailable (e.g. insecure context): nothing to do.
      });
  }, []);
  return [copied, copy];
}

function CopyIcon({ done }: { done: boolean }) {
  return done ? (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M20 6L9 17l-5-5" />
    </svg>
  ) : (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="9" width="12" height="12" rx="2.5" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export default function CommandBlock({ title = "kubectl", lines }: { title?: string; lines: string[] }) {
  const [copied, copy] = useCopy();
  const all = lines.join("\n");

  return (
    <div className="w-full overflow-hidden rounded-card bg-surface shadow-card">
      <div className="flex h-10 items-center gap-2 border-b border-line px-3 text-[12.5px]">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-ink-3" aria-hidden>
          <path d="M4 17l6-5-6-5M12 19h8" />
        </svg>
        <span className="truncate font-mono leading-none text-ink">{title}</span>
        {lines.length > 1 && (
          <button
            type="button"
            onClick={() => copy(all)}
            className={`-mr-1 ml-auto flex h-6 items-center gap-1 rounded-[6px] px-1.5 text-[12px] font-medium
              transition-colors duration-100 hover:bg-hover ${copied === all ? "text-green" : "text-ink-3 hover:text-ink"}`}
          >
            <CopyIcon done={copied === all} />
            {copied === all ? "Copied" : "Copy all"}
          </button>
        )}
      </div>

      <ol className="relative py-2 font-mono text-[12.5px] leading-[1.65] text-ink-2">
        <span className="pointer-events-none absolute inset-y-0 left-6 w-px bg-line" aria-hidden />
        {lines.map((line, i) => (
          <li key={i} className="group grid grid-cols-[24px_minmax(0,1fr)_auto] items-start">
            <span className="select-none pt-px text-center text-[11px] text-ink-3" aria-hidden>{i + 1}</span>
            <code className="pr-2 pl-2 break-words whitespace-pre-wrap">{highlight(line)}</code>
            <button
              type="button"
              onClick={() => copy(line)}
              aria-label={`Copy command ${i + 1}`}
              className={`mr-2 flex h-6 items-center rounded-[6px] px-1.5 transition-colors duration-100 hover:bg-hover
                ${copied === line ? "text-green" : "text-ink-3 hover:text-ink"}`}
            >
              <CopyIcon done={copied === line} />
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
