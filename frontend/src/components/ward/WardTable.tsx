"use client";
import clsx from "clsx";
import { BellRing, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import type { Bed } from "@/lib/api";
import { age, bedLabel, clock, mgdl, rate } from "@/lib/format";
import { stateStyle, TREND } from "@/lib/states";
import { InfoTag, QualityBadge, StatePill, Tip } from "@/components/ui/primitives";

// Wide (>= 1400 px): separate Quality column. Compact: quality shown under the reason.
const COLS =
  "grid grid-cols-[24px_minmax(84px,1fr)_140px_80px_80px_68px_minmax(150px,2fr)_76px_22px] items-center gap-x-2.5 min-[1400px]:grid-cols-[28px_minmax(96px,1fr)_148px_88px_92px_76px_minmax(170px,2fr)_minmax(150px,1.6fr)_84px_24px] min-[1400px]:gap-x-3";

function Reason({ bed }: { bed: Bed }) {
  const quiet = bed.decision.state === "NO_ALERT";
  return <span className={clsx("line-clamp-2 text-small", quiet ? "text-ink-4" : "text-ink-2")}>{bed.reason}</span>;
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
  return (
    <div
      role="row"
      onClick={() => router.push(href)}
      className={clsx(
        COLS,
        "relative cursor-pointer border-b border-line px-4 py-2.5 transition-colors last:border-b-0 hover:bg-[#fafbfc]",
        changed && "state-changed",
      )}
    >
      <span aria-hidden className={clsx("absolute inset-y-0 left-0 w-[3px]", s.bar)} />
      <span role="cell" className="text-small text-ink-4 tnum">{bed.rank}</span>
      <span role="cell" className="min-w-0">
        <Link
          href={href}
          onClick={(e) => e.stopPropagation()}
          aria-label={`${bedLabel(bed.recording_key, bed.label)}${bed.source === "NEW_DATA_SESSION" ? " (new data session)" : ""}: ${bed.summary}${bed.unacknowledged_notifications ? `; ${bed.unacknowledged_notifications} unacknowledged notifications` : ""}`}
          className="font-medium text-ink hover:text-accent hover:underline">
          {bedLabel(bed.recording_key, bed.label)}
        </Link>
        {bed.source === "NEW_DATA_SESSION" && (
          <span className="mt-0.5 block w-fit rounded-xs border border-watch-line bg-watch-tint px-1 text-[9.5px] font-semibold uppercase tracking-wide text-watch-ink">
            New data
          </span>
        )}
      </span>
      <span role="cell">
        <StatePill state={bed.decision.state} />
      </span>
      <span role="cell" className="text-right tnum">
        <span className={clsx("text-[15px] font-semibold", bed.cgm_low ? "text-low-ink" : "text-ink")}>
          {mgdl(bed.cgm_mgdl)}
        </span>
        <span className="ml-1 text-[10.5px] text-ink-4">mg/dL</span>
      </span>
      <span role="cell" className="text-small text-ink-2 tnum">
        {tr ? (
          <Tip content={`Trend ${tr.text} (${rate(bed.trend.rate_mgdl_per_min)} mg/dL/min, 30-min slope)`}>
            <span className="inline-flex items-center gap-1">
              <span aria-hidden className="w-5 font-semibold text-ink">{tr.glyph}</span>
              <span>{rate(bed.trend.rate_mgdl_per_min)}</span>
            </span>
          </Tip>
        ) : (
          <span className="text-ink-4">—</span>
        )}
      </span>
      <span role="cell" className="text-right tnum">
        {bed.decision.p_text ? (
          <span className={clsx("font-semibold", s.ink)}>{bed.decision.p_text}</span>
        ) : (
          <span className="text-small text-ink-4">no forecast</span>
        )}
      </span>
      <span role="cell" className="min-w-0">
        <Reason bed={bed} />
        {(bed.badges.length > 0 || bed.info_tags.length > 0) && (
          <span className="mt-1 flex min-w-0 flex-wrap gap-1 min-[1400px]:hidden">
            {bed.badges.map((b) => (
              <QualityBadge key={b} code={b} />
            ))}
            {bed.info_tags.slice(0, 1).map((t) => (
              <InfoTag key={t} tag={t} />
            ))}
          </span>
        )}
      </span>
      <span role="cell" className="hidden min-w-0 flex-wrap gap-1 overflow-hidden min-[1400px]:flex [&>*]:max-w-full [&>*]:truncate">
        {bed.badges.map((b) => (
          <QualityBadge key={b} code={b} />
        ))}
        {bed.info_tags.slice(0, bed.badges.length ? 1 : 2).map((t) => (
          <InfoTag key={t} tag={t} />
        ))}
        {bed.info_tags.length > (bed.badges.length ? 1 : 2) && (
          <Tip content={bed.info_tags.join(", ")}>
            <span className="text-[11px] text-ink-4">+{bed.info_tags.length - (bed.badges.length ? 1 : 2)}</span>
          </Tip>
        )}
      </span>
      <span role="cell" className="text-small tnum">
        <span className={clsx(bed.stale ? "font-medium text-alert-ink" : "text-ink-2")}>
          {age(bed.data_age_s)}
        </span>
        {bed.last_reading_ts !== null && <span className="block text-[11px] text-ink-4">{clock(bed.last_reading_ts, offsetS)}</span>}
      </span>
      <span role="cell" className="flex items-center justify-end">
        {bed.unacknowledged_notifications > 0 ? (
          <Tip content={`${bed.unacknowledged_notifications} notification(s) awaiting acknowledgement`}>
            <span className="relative inline-flex" aria-label={`${bed.unacknowledged_notifications} unacknowledged notifications`}>
              <BellRing aria-hidden className="size-4 text-alert" />
              <span className="absolute -right-1.5 -top-1.5 rounded-full bg-alert px-1 text-[9px] font-bold leading-[14px] text-white tnum">
                {bed.unacknowledged_notifications}
              </span>
            </span>
          </Tip>
        ) : (
          <ChevronRight aria-hidden className="size-4 text-ink-4" />
        )}
      </span>
    </div>
  );
}

export function WardTable({ beds, offsetS }: { beds: Bed[]; offsetS: number }) {
  return (
    <div role="table" aria-label="Ward board: beds ordered by policy state, then risk" className="overflow-x-auto rounded-lg border border-line bg-surface">
      <div className="min-w-[820px]">
        <div role="row" className={clsx(COLS, "border-b border-line bg-[#fafbfc] px-4 py-2")}>
          {["#", "Patient", "State", "CGM", "Trend", "Risk", "Reason", "Quality", "Updated", ""].map((h, i) => (
            <span key={i} role="columnheader" className={clsx("label-caps", (i === 3 || i === 5) && "text-right", i === 7 && "hidden min-[1400px]:block")}>
              {h}
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
