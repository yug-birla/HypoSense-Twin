"use client";
import clsx from "clsx";
import { ArrowRight, BellRing } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import type { Bed } from "@/lib/api";
import { age, bedLabel, clock, mgdl, rate } from "@/lib/format";
import { stateStyle, TREND } from "@/lib/states";
import { Help, InfoTag, QualityBadge, StatePill, Tip } from "@/components/ui/primitives";

const COLS = "grid grid-cols-[minmax(150px,1.3fr)_118px_120px_96px_minmax(170px,1.5fr)_110px_92px] items-center gap-x-4";

const AVATAR: Record<string, string> = {
  LOW_NOW: "bg-low-tint text-low-ink",
  ALERT: "bg-alert-tint text-alert-ink",
  WATCH: "bg-watch-tint text-watch-ink",
  NO_ALERT: "bg-mint text-mint-ink",
  INSUFFICIENT_DATA: "bg-sunken text-ink-3",
  SYSTEM_ERROR: "bg-error-tint text-error-ink",
};

/** Observed CGM of the last 2 h as a tiny line (display only), with the 70 mg/dL line. */
export function Sparkline({ points, falling, width = 110, height = 34 }: { points: [number, number][]; falling: boolean; width?: number; height?: number }) {
  if (!points || points.length < 2) return <span className="text-small text-ink-4">no recent readings</span>;
  const t0 = points[0]![0];
  const t1 = points[points.length - 1]![0];
  const lo = 40;
  const hi = Math.max(220, ...points.map((p) => p[1]));
  const x = (t: number) => (t1 === t0 ? 0 : ((t - t0) / (t1 - t0)) * (width - 4) + 2);
  const y = (v: number) => height - 2 - ((Math.min(Math.max(v, lo), hi) - lo) / (hi - lo)) * (height - 4);
  const d = points.map(([t, v], i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const color = falling ? "#e0457b" : "#1f9d64";
  return (
    <svg aria-hidden width={width} height={height} className="overflow-visible">
      <line x1={0} x2={width} y1={y(70)} y2={y(70)} stroke="#f2b8c6" strokeDasharray="3 3" strokeWidth={1} />
      <path d={`${d} L${x(t1).toFixed(1)},${height} L${x(t0).toFixed(1)},${height} Z`} fill={color} opacity={0.08} />
      <path d={d} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function Row({ bed, offsetS }: { bed: Bed; offsetS: number }) {
  const router = useRouter();
  const s = stateStyle(bed.decision.state);
  const prev = useRef(bed.decision.state);
  const changed = prev.current !== bed.decision.state;
  useEffect(() => {
    prev.current = bed.decision.state;
  }, [bed.decision.state]);
  const href = `/patient/?key=${encodeURIComponent(bed.recording_key)}`;
  const tr = bed.trend.category ? TREND[bed.trend.category] : undefined;
  const falling = (bed.delta_2h ?? 0) < 0 || (bed.trend.rate_mgdl_per_min ?? 0) < 0;
  const name = bedLabel(bed.recording_key, bed.label);
  const initials = (bed.label ?? bed.recording_key.split("_")[0] ?? "?").slice(-2).toUpperCase();
  return (
    <div
      role="row"
      onClick={() => router.push(href)}
      className={clsx(COLS, "relative cursor-pointer border-b border-line px-5 py-3 transition-colors last:border-b-0 hover:bg-sunken", changed && "state-changed")}
    >
      <span aria-hidden className={clsx("absolute inset-y-2 left-0 w-[3px] rounded-r", s.bar)} />
      <span role="cell" className="flex min-w-0 items-center gap-3">
        <span aria-hidden className={clsx("flex size-10 shrink-0 items-center justify-center rounded-full text-[13px] font-bold", AVATAR[bed.decision.state] ?? "bg-sunken text-ink-3")}>
          {initials}
        </span>
        <span className="min-w-0">
          <Link
            href={href}
            onClick={(e) => e.stopPropagation()}
            aria-label={`${name}${bed.source === "NEW_DATA_SESSION" ? " (new data session)" : ""}: ${bed.summary}${bed.unacknowledged_notifications ? `; ${bed.unacknowledged_notifications} unacknowledged notifications` : ""}`}
            className="block truncate text-[15px] font-semibold text-ink hover:text-accent hover:underline"
          >
            {name}
          </Link>
          <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12px] text-ink-3">
            {bed.source === "NEW_DATA_SESSION" ? (
              <span className="rounded-full border border-watch-line bg-watch-tint px-1.5 text-[10px] font-semibold uppercase tracking-wide text-watch-ink">New data</span>
            ) : (
              <span>Recorded replay</span>
            )}
            <span>· {bed.treated === null || bed.treated === undefined ? "regimen unknown" : bed.treated ? "Treated" : "Untreated"}</span>
          </span>
        </span>
      </span>
      <span role="cell" className="tnum">
        <span className="flex items-baseline gap-1">
          <span className={clsx("text-[20px] font-bold", bed.cgm_low ? "text-low-ink" : falling ? "text-alert-ink" : "text-ink")}>{mgdl(bed.cgm_mgdl)}</span>
          {tr && (
            <Tip content={`Trend ${tr.text} (${rate(bed.trend.rate_mgdl_per_min)} mg/dL per min, 30-min slope)`}>
              <span aria-label={`trend ${tr.text}`} className={clsx("text-[15px] font-bold", falling ? "text-alert-ink" : "text-mint-ink")}>
                {tr.glyph}
              </span>
            </Tip>
          )}
        </span>
        {bed.delta_2h !== null && bed.delta_2h !== undefined ? (
          <span className={clsx("mt-0.5 inline-block rounded-full px-2 text-[11px] font-medium", bed.delta_2h < 0 ? "bg-rose text-rose-ink" : "bg-mint text-mint-ink")}>
            {bed.delta_2h > 0 ? "+" : ""}
            {Math.round(bed.delta_2h)} (2h)
          </span>
        ) : (
          <span className="block text-[11px] text-ink-4">mg/dL</span>
        )}
      </span>
      <span role="cell">
        <Sparkline points={bed.spark as [number, number][]} falling={falling} />
      </span>
      <span role="cell" className="tnum">
        {bed.decision.p_text ? (
          <span className={clsx("text-[17px] font-bold", s.ink)}>{bed.decision.p_text}</span>
        ) : (
          <span className="text-small text-ink-4">{bed.decision.state === "LOW_NOW" ? "observed low" : "no forecast"}</span>
        )}
      </span>
      <span role="cell" className="min-w-0">
        <StatePill state={bed.decision.state} explain />
        <span className={clsx("mt-1 line-clamp-2 text-[12px]", bed.decision.state === "NO_ALERT" ? "text-ink-4" : "text-ink-3")}>{bed.reason}</span>
        {(bed.badges.length > 0 || bed.info_tags.length > 0) && (
          <span className="mt-1 flex min-w-0 flex-wrap gap-1">
            {bed.badges.map((b) => (
              <QualityBadge key={b} code={b} />
            ))}
            {bed.info_tags.slice(0, 1).map((t) => (
              <InfoTag key={t} tag={t} />
            ))}
          </span>
        )}
      </span>
      <span role="cell" className="text-small tnum">
        {bed.last_reading_ts !== null && <span className="block font-medium text-ink-2">{clock(bed.last_reading_ts, offsetS)}</span>}
        <span className={clsx("block", bed.stale ? "font-medium text-alert-ink" : "text-ink-4")}>
          {bed.stale ? `not current · ${age(bed.data_age_s)}` : age(bed.data_age_s)}
        </span>
      </span>
      <span role="cell" className="flex items-center justify-end gap-2">
        {bed.unacknowledged_notifications > 0 && (
          <Tip content={`${bed.unacknowledged_notifications} notification(s) awaiting acknowledgement`}>
            <span className="relative inline-flex" aria-label={`${bed.unacknowledged_notifications} unacknowledged notifications`}>
              <BellRing aria-hidden className="size-4 text-alert" />
              <span className="absolute -right-1.5 -top-1.5 rounded-full bg-alert px-1 text-[9px] font-bold leading-[14px] text-white tnum">
                {bed.unacknowledged_notifications}
              </span>
            </span>
          </Tip>
        )}
        <span aria-hidden className="inline-flex h-8 items-center gap-1 rounded-full bg-accent-soft px-3 text-small font-semibold text-accent">
          Open <ArrowRight className="size-3.5" />
        </span>
      </span>
    </div>
  );
}

const HEADERS: [string, string | null][] = [
  ["Patient", null],
  ["Glucose now", "The latest observed CGM reading (mg/dL), its 30-minute trend and the change over the last 2 hours."],
  ["Last 2 hours", "Observed CGM over the last 2 hours; the dashed line is 70 mg/dL."],
  ["Risk 60 min", "Model-estimated chance that a new CGM-detected low (< 70 mg/dL) begins within 60 minutes. Development model, not clinically validated. Shown only when a forecast is possible."],
  ["Status", "Decided by fixed rules on the server. LOW NOW is observed; ALERT / WATCH / NO ALERT are predictions for the next 60 min; INSUFFICIENT DATA means no forecast is possible. Hover a status for its meaning."],
  ["Last reading", "Time and age of the latest CGM reading at the replay clock. Older than 20 min = not current, and no forecast is shown."],
  ["", null],
];

export function WardTable({ beds, offsetS }: { beds: Bed[]; offsetS: number }) {
  return (
    <div role="table" aria-label="Ward board: beds ordered by policy state, then risk" className="card overflow-x-auto">
      <div className="min-w-[1000px]">
        <div role="row" className={clsx(COLS, "border-b border-line px-5 py-3")}>
          {HEADERS.map(([h, help], i) => (
            <span key={i} role="columnheader" className="flex items-center gap-1 text-[12px] font-semibold text-ink-3">
              {h}
              {help && <Help label={`About ${h}`}>{help}</Help>}
            </span>
          ))}
        </div>
        <div role="rowgroup">
          {beds.map((b) => (
            <Row key={b.recording_key} bed={b} offsetS={offsetS} />
          ))}
        </div>
      </div>
    </div>
  );
}
