"use client";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, ChevronRight, CircleDashed, Lightbulb, Users } from "lucide-react";
import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import type { Bed, Ward } from "@/lib/api";
import { age, bedLabel, mgdl } from "@/lib/format";
import { useConnectionLost, useDataOffset, useStatus, useWard } from "@/lib/queries";
import { STATE } from "@/lib/states";
import { PageHeader } from "@/components/shell/AppShell";
import { ReplayBar } from "@/components/replay/ReplayBar";
import { CasePicker } from "@/components/ward/CasePicker";
import { WardTable } from "@/components/ward/WardTable";
import { Button, Empty, ErrorBox, Panel, Skeleton } from "@/components/ui/primitives";

type Filter = "all" | "attention" | "ALERT" | "WATCH" | "NO_ALERT" | "LOW_NOW" | "none";
const FILTERS: { id: Filter; label: string; match: (b: Bed) => boolean }[] = [
  { id: "all", label: "All", match: () => true },
  { id: "attention", label: "Need attention", match: (b) => STATE[b.decision.state as keyof typeof STATE]?.attention ?? true },
  { id: "LOW_NOW", label: "Low now", match: (b) => b.decision.state === "LOW_NOW" },
  { id: "ALERT", label: "Alert", match: (b) => b.decision.state === "ALERT" },
  { id: "WATCH", label: "Watch", match: (b) => b.decision.state === "WATCH" },
  { id: "NO_ALERT", label: "No alert", match: (b) => b.decision.state === "NO_ALERT" },
  { id: "none", label: "No forecast", match: (b) => b.decision.state === "INSUFFICIENT_DATA" || b.decision.state === "SYSTEM_ERROR" },
];

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning!" : h < 18 ? "Good afternoon!" : "Good evening!";
}

function Tile({ icon, value, label, tone, onClick, active }: { icon: ReactNode; value: number; label: string; tone: string; onClick: () => void; active: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={clsx("card flex items-center gap-4 px-5 py-4 text-left transition-shadow hover:shadow-md", active && "ring-2 ring-accent")}
    >
      <span className={clsx("flex size-12 shrink-0 items-center justify-center rounded-2xl", tone)}>{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[28px] font-bold leading-none text-ink tnum">{value}</span>
        <span className="mt-1 block text-small text-ink-3">{label}</span>
      </span>
      <ChevronRight aria-hidden className="size-4 text-ink-4" />
    </button>
  );
}

/** Where every patient's latest observed CGM sits relative to 70 and 180 mg/dL. */
function GlucoseNow({ beds }: { beds: Bed[] }) {
  const pts = beds.filter((b) => b.cgm_mgdl !== null && !b.stale);
  const x = (v: number) => `${(Math.min(Math.max(v, 40), 300) - 40) / 2.6}%`;
  return (
    <Panel title="Glucose now, all patients">
      <div className="relative mt-2 h-14">
        <div className="absolute inset-x-0 top-6 h-3 rounded-full bg-sunken" />
        <div className="absolute top-6 h-3 bg-mint" style={{ left: x(70), width: `calc(${x(180)} - ${x(70)})` }} />
        <div className="absolute top-6 h-3 rounded-l-full bg-rose" style={{ left: 0, width: x(70) }} />
        {pts.map((b) => (
          <span
            key={b.recording_key}
            title={`${bedLabel(b.recording_key, b.label)}: ${mgdl(b.cgm_mgdl)} mg/dL`}
            className={clsx("absolute top-[18px] size-4 -translate-x-1/2 rounded-full border-2 border-white shadow", b.cgm_low ? "bg-low" : "bg-accent")}
            style={{ left: x(b.cgm_mgdl!) }}
          />
        ))}
        <span className="absolute top-10 -translate-x-1/2 text-[11px] text-ink-3" style={{ left: x(70) }}>70</span>
        <span className="absolute top-10 -translate-x-1/2 text-[11px] text-ink-3" style={{ left: x(180) }}>180</span>
      </div>
      <p className="mt-1 text-[12px] text-ink-3">
        Latest observed reading per patient (mg/dL); {beds.length - pts.length} without a current reading.
      </p>
    </Panel>
  );
}

function Insights({ beds }: { beds: Bed[] }) {
  const alert = beds.filter((b) => b.decision.state === "ALERT" || b.decision.state === "WATCH").length;
  const low = beds.filter((b) => b.decision.state === "LOW_NOW").length;
  const none = beds.filter((b) => b.decision.p === null && b.decision.state !== "LOW_NOW").length;
  const unack = beds.reduce((a, b) => a + b.unacknowledged_notifications, 0);
  const lines = [
    low ? `${low} patient${low > 1 ? "s have" : " has"} an observed low now — capillary confirmation per local protocol.` : null,
    alert ? `${alert} patient${alert > 1 ? "s have" : " has"} an elevated estimated risk for the next 60 minutes.` : null,
    unack ? `${unack} alert notification${unack > 1 ? "s are" : " is"} waiting to be acknowledged.` : null,
    none ? `${none} patient${none > 1 ? "s have" : " has"} no forecast right now (not enough recent data).` : null,
  ].filter(Boolean) as string[];
  return (
    <div className="card relative overflow-hidden bg-gradient-to-br from-[#fff8ec] to-[#fff1f6] p-5">
      <p className="flex items-center gap-2 text-section font-bold text-ink">
        <Lightbulb aria-hidden className="size-5 text-peach-ink" /> Twin insights
      </p>
      <ul className="mt-2 flex flex-col gap-1.5 text-small text-ink-2">
        {lines.length ? lines.map((l) => <li key={l}>{l}</li>) : <li>Everyone is below the watch threshold right now.</li>}
      </ul>
      <p className="mt-2 text-[11px] text-ink-4">Counts of the server’s current states; no new judgement is made here.</p>
    </div>
  );
}

function Events({ ward }: { ward: Ward }) {
  return (
    <Panel title="Recent events">
      {(ward.events ?? []).length === 0 ? (
        <p className="text-small text-ink-3">No state changes yet.</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {(ward.events ?? []).map((e) => (
            <li key={`${e.recording_key}-${e.ts}-${e.kind}`} className="flex gap-3">
              <span aria-hidden className={clsx("mt-1.5 size-2.5 shrink-0 rounded-full", STATE[e.state as keyof typeof STATE]?.bar ?? "bg-line-strong", e.state === "NO_ALERT" && "bg-mint-ink")} />
              <span className="min-w-0 text-small">
                <Link href={`/patient/?key=${encodeURIComponent(e.recording_key)}`} className="font-semibold text-ink hover:text-accent">
                  {bedLabel(e.recording_key, e.label)}
                </Link>{" "}
                <span className="text-ink-2">
                  {e.kind === "notification" ? "ALERT notification" : `now ${STATE[e.state as keyof typeof STATE]?.label ?? e.state}`}
                </span>
                <span className="block text-[12px] text-ink-3 tnum">
                  {age(e.age_s)}
                  {e.p_text ? ` · risk ${e.p_text}` : ""}
                  {e.cgm_mgdl !== null ? ` · ${mgdl(e.cgm_mgdl)} mg/dL` : ""}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

export default function WardPage() {
  const status = useStatus();
  const ward = useWard();
  const offset = useDataOffset();
  const lost = useConnectionLost() || ward.isError;
  const [picking, setPicking] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const hasSession = (status.data?.recordings.length ?? 0) > 0;
  const beds = useMemo(() => ward.data?.beds ?? [], [ward.data]);
  const liveBeds = beds.filter((b) => b.source === "NEW_DATA_SESSION").length;
  const showWard = (hasSession && !picking) || liveBeds > 0;
  const count = (f: Filter) => beds.filter(FILTERS.find((x) => x.id === f)!.match).length;
  const shown = beds.filter(FILTERS.find((x) => x.id === filter)!.match);
  const attention = count("attention");

  return (
    <div>
      <PageHeader
        title={beds.length ? greeting() : "Ward board"}
        sub={beds.length ? "Here is who needs attention right now. Patients are ordered by status, then by estimated risk." : "Replay recorded patients and see who needs attention, minute by minute."}
        bubble={beds.length ? `${beds.length} patients in view. ${attention} need${attention === 1 ? "s" : ""} your attention.` : "Start a replay to fill the ward."}
        aside={
          hasSession && !picking ? (
            <Button size="sm" onClick={() => setPicking(true)}>
              Change recordings
            </Button>
          ) : undefined
        }
      />
      <div className="flex flex-col gap-5 p-6">
        {status.isError && <ErrorBox title="HypoSense service unavailable" detail="Start it with `hyposense serve`." onRetry={() => status.refetch()} />}
        {(!hasSession || picking) && status.isSuccess && <CasePicker onDone={() => setPicking(false)} />}
        {showWard && (
          <>
            {hasSession && !picking && <ReplayBar compact />}
            {ward.isError && <ErrorBox title="Ward unavailable" detail={(ward.error as Error).message} onRetry={() => ward.refetch()} />}
            {!ward.data && !ward.isError && <Skeleton className="h-64 w-full" />}
            {ward.data && beds.length > 0 && lost && (
              <Empty title="Ward state not current">
                The service or stream is unreachable, so bed states are hidden rather than shown out of date. They return as soon as
                the connection is restored.
              </Empty>
            )}
            {ward.data && beds.length > 0 && !lost && (
              <div className="grid grid-cols-1 gap-5 2xl:grid-cols-[minmax(0,1fr)_320px]">
                <div className="flex min-w-0 flex-col gap-4">
                  <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                    <Tile icon={<Users aria-hidden className="size-6 text-accent" />} tone="bg-accent-soft" value={beds.length} label="Patients on the board" onClick={() => setFilter("all")} active={filter === "all"} />
                    <Tile icon={<AlertTriangle aria-hidden className="size-6 text-alert" />} tone="bg-alert-tint" value={attention} label="Need attention" onClick={() => setFilter("attention")} active={filter === "attention"} />
                    <Tile icon={<CheckCircle2 aria-hidden className="size-6 text-mint-ink" />} tone="bg-mint" value={count("NO_ALERT")} label="No alert" onClick={() => setFilter("NO_ALERT")} active={filter === "NO_ALERT"} />
                    <Tile icon={<CircleDashed aria-hidden className="size-6 text-ink-3" />} tone="bg-sunken" value={count("none")} label="No forecast possible" onClick={() => setFilter("none")} active={filter === "none"} />
                  </div>
                  <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-2">
                    {FILTERS.map((f) => (
                      <button
                        key={f.id}
                        type="button"
                        aria-pressed={filter === f.id}
                        onClick={() => setFilter(f.id)}
                        className={clsx(
                          "h-9 rounded-full border px-4 text-small font-medium transition-colors",
                          filter === f.id ? "border-accent bg-accent-soft text-accent" : "border-line bg-surface text-ink-2 hover:border-line-strong",
                        )}
                      >
                        {f.label} ({count(f.id)})
                      </button>
                    ))}
                  </div>
                  {shown.length ? (
                    <WardTable beds={shown} offsetS={offset} />
                  ) : (
                    <Empty title="No patient matches this filter" />
                  )}
                  <p className="text-[12px] text-ink-4">
                    LOW NOW is an observed reading; ALERT, WATCH and NO ALERT are predictions for the next 60 minutes from a DEVELOPMENT
                    model (not clinically validated). Times are each recording’s own clock. Patients marked NEW DATA are separate sessions
                    you added, never part of the research evidence.
                  </p>
                </div>
                <div className="grid grid-cols-1 content-start gap-4 xl:grid-cols-3 2xl:grid-cols-1">
                  <GlucoseNow beds={beds} />
                  <Insights beds={beds} />
                  <Events ward={ward.data} />
                </div>
              </div>
            )}
            {ward.data && beds.length === 0 && <Empty title="No beds in this replay" />}
          </>
        )}
      </div>
    </div>
  );
}
