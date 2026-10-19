"use client";
// Fixed questions about the displayed state. Answers are composed by the backend from fields the
// twin already holds; no free text is accepted and nothing is generated.
import { useState } from "react";
import { api, ApiError, type AskAnswer } from "@/lib/api";
import { Panel } from "@/components/ui/primitives";

const INTENTS: [string, string][] = [
  ["why_state", "Why this status?"],
  ["no_forecast", "Why (no) forecast?"],
  ["current", "Are readings current?"],
  ["changed", "What changed?"],
  ["after_alert", "After the last alert?"],
  ["medications", "Which medicines are recorded?"],
  ["quality", "What do warnings mean?"],
  ["missing", "What is missing?"],
  ["evidence", "What supports this?"],
];

export function AskPanel({ k }: { k: string }) {
  const [ans, setAns] = useState<AskAnswer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ask = async (intent: string) => {
    setBusy(true);
    setErr(null);
    try {
      setAns(await api.ask(k, intent));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Unexpected error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Ask about this patient" aside={<span className="text-[11px] text-ink-4">answers from recorded data only</span>}>
      <div className="flex flex-wrap gap-1.5">
        {INTENTS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            disabled={busy}
            aria-pressed={ans?.intent === id}
            onClick={() => void ask(id)}
            className={
              ans?.intent === id
                ? "h-7 rounded-md bg-ink px-2.5 text-small font-medium text-white"
                : "h-7 rounded-md border border-line-strong px-2.5 text-small text-ink-2 hover:bg-sunken"
            }
          >
            {label}
          </button>
        ))}
      </div>
      {err && <p role="alert" className="mt-2 text-small text-error-ink">{err}</p>}
      {ans && (
        <div className="mt-3" aria-live="polite">
          <p className="text-small font-semibold text-ink">{ans.question}</p>
          <ul className="mt-1 flex list-disc flex-col gap-1 pl-4 text-small text-ink-2">
            {ans.lines.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-2 text-[11px] text-ink-4">
        Answers are assembled from what the twin has recorded — no chatbot, no free text, no medical advice. If something is not
        known, the answer says so.
      </p>
    </Panel>
  );
}
