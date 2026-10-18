"use client";
import { useState } from "react";
import type { Bed } from "@/lib/api";
import { useConnectionLost, useDataOffset, useStatus, useWard } from "@/lib/queries";
import { STATE, type PolicyState } from "@/lib/states";
import { PageHeader } from "@/components/shell/AppShell";
import { ReplayBar } from "@/components/replay/ReplayBar";
import { CasePicker } from "@/components/ward/CasePicker";
import { WardTable } from "@/components/ward/WardTable";
import { Button, Empty, ErrorBox, Skeleton, StatePill } from "@/components/ui/primitives";

const ORDER: PolicyState[] = ["SYSTEM_ERROR", "LOW_NOW", "ALERT", "WATCH", "INSUFFICIENT_DATA", "NO_ALERT"];

function AttentionSummary({ beds }: { beds: Bed[] }) {
  const counts = ORDER.map((s) => [s, beds.filter((b) => b.decision.state === s).length] as const);
  const attention = counts.filter(([s, n]) => STATE[s].attention && n > 0).reduce((a, [, n]) => a + n, 0);
  const quality = beds.filter((b) => b.badges.length > 0).length;
  const unack = beds.reduce((a, b) => a + b.unacknowledged_notifications, 0);
  return (
    <div className="grid grid-cols-[auto_1fr_auto] items-center gap-5 rounded-lg border border-line bg-surface px-5 py-3.5">
      <div>
        <p className="label-caps">Need attention</p>
        <p className="text-metric font-semibold text-ink tnum">
          {attention}
          <span className="ml-1.5 text-body font-normal text-ink-3">of {beds.length} beds</span>
        </p>
      </div>
      <ul className="grid grid-cols-3 gap-x-4 gap-y-2 2xl:flex 2xl:flex-wrap 2xl:items-center" aria-label="Beds by state">
        {counts.map(([s, n]) => (
          <li key={s}>
            <span className="inline-flex items-center gap-1.5">
              <StatePill state={s} size="sm" muted={n === 0} />
              <span className={n === 0 ? "text-body text-ink-3 tnum" : "text-body font-semibold text-ink tnum"}>{n}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="flex gap-5 border-l border-line pl-5">
        <div>
          <p className="label-caps">Quality issues</p>
          <p className="text-title font-semibold text-ink tnum">{quality}</p>
        </div>
        <div>
          <p className="label-caps">Unacknowledged</p>
          <p className="text-title font-semibold text-ink tnum">{unack}</p>
        </div>
      </div>
    </div>
  );
}

export default function WardPage() {
  const status = useStatus();
  const ward = useWard();
  const offset = useDataOffset();
  const lost = useConnectionLost() || ward.isError;
  const [picking, setPicking] = useState(false);
  const hasSession = (status.data?.recordings.length ?? 0) > 0;

  return (
    <div>
      <PageHeader
        title="Ward board"
        sub="Who needs attention now. Ordered by policy state, then estimated risk (server-side)."
        aside={
          hasSession && !picking ? (
            <Button size="sm" onClick={() => setPicking(true)}>
              Change cases
            </Button>
          ) : undefined
        }
      />
      <div className="flex flex-col gap-4 p-6">
        {status.isError && <ErrorBox title="HypoSense service unavailable" detail="Start it with `hyposense serve`." onRetry={() => status.refetch()} />}
        {(!hasSession || picking) && status.isSuccess && <CasePicker onDone={() => setPicking(false)} />}
        {hasSession && !picking && (
          <>
            <ReplayBar />
            {ward.isError && <ErrorBox title="Ward unavailable" detail={(ward.error as Error).message} onRetry={() => ward.refetch()} />}
            {!ward.data && !ward.isError && <Skeleton className="h-64 w-full" />}
            {ward.data && ward.data.beds.length > 0 && lost && (
              <Empty title="Ward state not current">
                The service or stream is unreachable, so bed states are hidden rather than shown out of date. They
                return as soon as the connection is restored.
              </Empty>
            )}
            {ward.data && ward.data.beds.length > 0 && !lost && (
              <>
                <AttentionSummary beds={ward.data.beds} />
                <WardTable beds={ward.data.beds} offsetS={offset} />
                <p className="text-[11.5px] text-ink-4">
                  Risk = model-estimated probability of a CGM-detected low within 60 minutes (DEVELOPMENT model). States
                  are decided by the backend policy; LOW NOW always reflects an observed reading. Times are the record’s
                  local clock.
                </p>
              </>
            )}
            {ward.data && ward.data.beds.length === 0 && <Empty title="No beds in this replay" />}
          </>
        )}
      </div>
    </div>
  );
}
