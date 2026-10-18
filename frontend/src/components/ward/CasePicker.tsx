"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError, type Case } from "@/lib/api";
import { bedLabel } from "@/lib/format";
import { useCases } from "@/lib/queries";
import { Button, ErrorBox, Panel, Skeleton } from "@/components/ui/primitives";

const MAX = 12;
const DEFAULT_N = 8;

/** Case selection (T partition only, served by the backend catalogue). The default is the first
 *  recordings in catalogue order: deterministic, never chosen for how the model performs. */
export function CasePicker({ onDone }: { onDone?: () => void }) {
  const qc = useQueryClient();
  const cases = useCases();
  const [sel, setSel] = useState<string[] | null>(null);
  const start = useMutation({
    mutationFn: (keys: string[]) => api.select(keys),
    onSuccess: () => {
      qc.invalidateQueries();
      onDone?.();
    },
  });
  if (cases.isError) return <ErrorBox title="Cases unavailable" detail={(cases.error as Error).message} onRetry={() => cases.refetch()} />;
  if (!cases.data) return <Skeleton className="h-40 w-full" />;
  const list: Case[] = cases.data;
  const chosen = sel ?? list.slice(0, DEFAULT_N).map((c) => c.recording_key);
  const toggle = (k: string) =>
    setSel(chosen.includes(k) ? chosen.filter((x) => x !== k) : chosen.length < MAX ? [...chosen, k] : chosen);
  return (
    <Panel
      title="Start a ward replay"
      aside={<span className="text-small text-ink-3 tnum">{chosen.length} / {MAX} selected</span>}
    >
      <p className="mb-3 max-w-3xl text-small text-ink-3">
        Recordings from the tuning partition (T). The evaluation partition is sealed and never offered. The default
        selection is the first {DEFAULT_N} recordings in catalogue order; it is not chosen by model performance.
      </p>
      <fieldset className="grid grid-cols-[repeat(auto-fill,minmax(168px,1fr))] gap-1.5">
        <legend className="sr-only">Recordings</legend>
        {list.map((c) => (
          <label
            key={c.recording_key}
            className="flex cursor-pointer items-center gap-2 rounded-md border border-line px-2.5 py-1.5 text-small hover:bg-sunken has-[:checked]:border-accent has-[:checked]:bg-accent-soft"
          >
            <input type="checkbox" className="accent-[var(--color-accent)]" checked={chosen.includes(c.recording_key)} onChange={() => toggle(c.recording_key)} />
            <span className="font-medium text-ink">{bedLabel(c.recording_key)}</span>
            <span className="ml-auto text-ink-4 tnum">{c.days.toFixed(1)} d</span>
          </label>
        ))}
      </fieldset>
      <div className="mt-4 flex items-center gap-3">
        <Button variant="primary" disabled={chosen.length === 0 || start.isPending} onClick={() => start.mutate(chosen)}>
          {start.isPending ? "Loading…" : "Start replay"}
        </Button>
        {start.isError && <span className="text-small text-low-ink">{start.error instanceof ApiError ? start.error.message : "Could not start."}</span>}
      </div>
    </Panel>
  );
}
