"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Pause, Play, RotateCcw, StepForward } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { duration } from "@/lib/format";
import { useConnectionLost, useStatus } from "@/lib/queries";
import { Button, Tip } from "@/components/ui/primitives";

const SPEEDS = [60, 120, 600, 1800];

/** Replay controller. Drives the backend replay clock only; event order is fixed server-side. */
export function ReplayBar({ compact = false }: { compact?: boolean }) {
  const qc = useQueryClient();
  const status = useStatus();
  const s = status.data;
  const [drag, setDrag] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: (f: () => Promise<unknown>) => f(),
    onSuccess: () => {
      setErr(null);
      qc.invalidateQueries({ queryKey: ["status"] });
      qc.invalidateQueries({ queryKey: ["ward"] });
      qc.invalidateQueries({ queryKey: ["patient"] });
    },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "Replay command failed."),
    onSettled: () => setDrag(null), // F9: never leave the slider on a value that was not applied
  });
  const lost = useConnectionLost();

  useEffect(() => {
    if (drag !== null && !run.isPending) setDrag(null);
  }, [s?.offset_s]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!s || s.recordings.length === 0) return null;
  const busy = run.isPending || lost;
  const offset = drag ?? s.offset_s;
  const pctDone = s.duration_s ? (100 * offset) / s.duration_s : 0;

  return (
    <div
      role="group"
      aria-label="Replay controls"
      className={clsx("flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface px-3 py-2", compact && "py-1.5")}
    >
      <span className="label-caps hidden text-ink-3 lg:inline">Replay of recorded data</span>
      <div className="flex items-center gap-1">
        {s.playing ? (
          <Button size="sm" variant="primary" aria-label="Pause replay" disabled={busy} onClick={() => run.mutate(api.pause)}>
            <Pause aria-hidden className="size-3.5" /> Pause
          </Button>
        ) : (
          <Button size="sm" variant="primary" aria-label="Play replay" disabled={busy || s.finished} onClick={() => run.mutate(api.play)}>
            <Play aria-hidden className="size-3.5" /> Play
          </Button>
        )}
        <Tip content="Process the next recorded event">
          <Button size="sm" aria-label="Step one event" disabled={busy || s.playing || s.finished} onClick={() => run.mutate(() => api.step(1))}>
            <StepForward aria-hidden className="size-3.5" /> {compact ? "" : "Next event"}
          </Button>
        </Tip>
        <Tip content="Advance 1 hour of data time">
          <Button size="sm" aria-label="Advance one hour" disabled={busy || s.playing || s.finished} onClick={() => run.mutate(() => api.advance(3600))}>
            +1 hour
          </Button>
        </Tip>
        <Tip content="Restart from the beginning (deterministic rebuild)">
          <Button size="sm" variant="ghost" aria-label="Reset replay" disabled={busy} onClick={() => run.mutate(api.reset)}>
            <RotateCcw aria-hidden className="size-3.5" />
          </Button>
        </Tip>
      </div>

      <label className="flex items-center gap-1.5 text-small text-ink-3">
        <span>Speed</span>
        <select
          className="h-7 rounded-md border border-line-strong bg-surface px-1.5 text-small text-ink tnum"
          value={s.speed}
          disabled={busy}
          onChange={(e) => run.mutate(() => api.speed(Number(e.target.value)))}
        >
          {SPEEDS.map((v) => (
            <option key={v} value={v}>
              ×{v} ({v / 60} min of data per second)
            </option>
          ))}
          {!SPEEDS.includes(s.speed) && <option value={s.speed}>×{s.speed}</option>}
        </select>
      </label>

      <div className="flex min-w-[220px] flex-1 items-center gap-2">
        <span className="w-[86px] text-right text-small text-ink-2 tnum" title="Time elapsed since the start of each recording">{duration(offset)}</span>
        <input
          type="range"
          aria-label="Replay position"
          min={0}
          max={s.duration_s}
          step={900}
          value={offset}
          disabled={busy || s.playing}
          onChange={(e) => setDrag(Number(e.target.value))}
          onPointerUp={() => drag !== null && run.mutate(() => api.seek(drag))}
          onKeyUp={(e) => (e.key.startsWith("Arrow") || e.key === "Home" || e.key === "End") && drag !== null && run.mutate(() => api.seek(drag))}
          className="h-1.5 flex-1 cursor-pointer accent-[var(--color-accent)]"
          style={{ background: `linear-gradient(to right, var(--color-accent) ${pctDone}%, var(--color-line) ${pctDone}%)` }}
        />
        <span className="w-[64px] text-small text-ink-3 tnum" title="Length of the longest selected recording">{duration(s.duration_s)}</span>
      </div>

      <div className="flex items-center gap-2 text-small text-ink-3">
        <span className={clsx("size-1.5 rounded-full", s.playing ? "bg-accent" : s.finished ? "bg-ink-4" : "bg-watch")} aria-hidden />
        {busy ? "Working…" : s.playing ? "Playing" : s.finished ? "Finished" : "Paused"}
      </div>
      {err && (
        <p role="alert" className="w-full text-small text-low-ink">
          {err}
        </p>
      )}
    </div>
  );
}
