"use client";
import clsx from "clsx";
import { ChevronLeft, ChevronRight, Minus, PlayCircle, X } from "lucide-react";
import { useState } from "react";
import { STEPS, useDemo } from "@/lib/demo";
import { Button } from "@/components/ui/primitives";

/** Floating guide shown on every page while the guided demo is active. */
export function DemoDock() {
  const d = useDemo();
  const [min, setMin] = useState(false);
  if (!d.active) return null;
  if (min)
    return (
      <button
        type="button"
        onClick={() => setMin(false)}
        className="fixed bottom-4 right-4 z-40 inline-flex items-center gap-2 rounded-full border border-ink/15 bg-surface px-4 py-2 text-small font-semibold text-ink shadow-[0_8px_24px_rgba(16,24,40,0.16)]"
      >
        <PlayCircle aria-hidden className="size-4 text-accent" /> Guided demo · step {d.step + 1} of {STEPS.length} — show
      </button>
    );
  const s = STEPS[d.step]!;
  const last = d.step === STEPS.length - 1;
  const needs = !!s.action && !d.done[d.step];
  return (
    <aside
      aria-label="Guided demo"
      className="fixed bottom-4 right-4 z-40 w-[380px] max-w-[calc(100vw-2rem)] rounded-lg border border-ink/15 bg-surface shadow-[0_12px_32px_rgba(16,24,40,0.18)]"
    >
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <PlayCircle aria-hidden className="size-4 text-accent" />
        <p className="text-small font-semibold text-ink">
          Guided demo · step {d.step + 1} of {STEPS.length}
        </p>
        <button type="button" aria-label="Minimise guided demo" onClick={() => setMin(true)} className="ml-auto rounded p-1 text-ink-3 hover:bg-sunken hover:text-ink">
          <Minus aria-hidden className="size-4" />
        </button>
        <button type="button" aria-label="Exit guided demo" onClick={d.exit} className="rounded p-1 text-ink-3 hover:bg-sunken hover:text-ink">
          <X aria-hidden className="size-4" />
        </button>
      </div>
      <div className="flex flex-col gap-2 px-4 py-3">
        <h2 className="text-[15px] font-semibold text-ink">{s.title}</h2>
        <p className="text-small leading-relaxed text-ink-2">{s.body}</p>
        {s.action && (
          <Button variant={needs ? "primary" : "secondary"} disabled={d.busy || !needs} onClick={() => void d.run()}>
            {d.busy ? "Working…" : d.done[d.step] ? "Done" : s.action}
          </Button>
        )}
        {d.message && (
          <p role="status" className="rounded-md bg-accent-soft px-2.5 py-1.5 text-small text-ink">
            {d.message}
          </p>
        )}
        {d.error && (
          <p role="alert" className="text-small text-error-ink">
            {d.error}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 border-t border-line px-4 py-2.5">
        <Button size="sm" variant="ghost" disabled={d.step === 0 || d.busy} onClick={() => d.go(d.step - 1)}>
          <ChevronLeft aria-hidden className="size-3.5" /> Back
        </Button>
        <ol aria-hidden className="mx-auto flex gap-1">
          {STEPS.map((_, i) => (
            <li key={i} className={clsx("size-1.5 rounded-full", i === d.step ? "bg-accent" : i < d.step ? "bg-ink-3" : "bg-line-strong")} />
          ))}
        </ol>
        {last ? (
          <Button size="sm" variant="primary" onClick={d.exit}>
            Finish
          </Button>
        ) : (
          <Button size="sm" variant={needs ? "secondary" : "primary"} disabled={d.busy || needs} onClick={() => d.go(d.step + 1)}>
            Next <ChevronRight aria-hidden className="size-3.5" />
          </Button>
        )}
      </div>
    </aside>
  );
}
