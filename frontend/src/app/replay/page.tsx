"use client";
import { ArrowRight, PlayCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { bedLabel, mgdl } from "@/lib/format";
import { useStatus, useWard } from "@/lib/queries";
import { PageHeader } from "@/components/shell/AppShell";
import { ReplayBar } from "@/components/replay/ReplayBar";
import { CasePicker } from "@/components/ward/CasePicker";
import { Sparkline } from "@/components/ward/WardTable";
import { Button, Panel, StatePill } from "@/components/ui/primitives";

export default function ReplayStudio() {
  const status = useStatus();
  const ward = useWard();
  const [picking, setPicking] = useState(false);
  const has = (status.data?.recordings.length ?? 0) > 0;
  const beds = (ward.data?.beds ?? []).filter((b) => b.source !== "NEW_DATA_SESSION");
  return (
    <div>
      <PageHeader
        title="Replay studio"
        sub="Play recorded patients through the twin in time order, as if their readings were arriving live. The order is fixed by the data; nothing is staged."
        bubble="Same data, same order, same decisions — every time."
        aside={
          <Link href="/demo/" className="inline-flex h-10 items-center gap-2 rounded-full bg-accent px-5 text-body font-semibold text-white">
            <PlayCircle aria-hidden className="size-4" /> Prefer a guided tour? Start the guided demo
          </Link>
        }
      />
      <div className="flex flex-col gap-5 p-6">
        {(!has || picking) && status.isSuccess && <CasePicker onDone={() => setPicking(false)} />}
        {has && !picking && (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <div className="min-w-0 flex-1">
                <ReplayBar />
              </div>
              <Button onClick={() => setPicking(true)}>Change recordings</Button>
            </div>
            <Panel
              title="Patients in this replay"
              aside={
                <Link href="/ward/" className="inline-flex items-center gap-1 text-small font-semibold text-accent hover:underline">
                  Open the ward board <ArrowRight aria-hidden className="size-3.5" />
                </Link>
              }
            >
              <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-4">
                {beds.map((b) => (
                  <li key={b.recording_key}>
                    <Link href={`/patient/?key=${encodeURIComponent(b.recording_key)}`} className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-4 hover:border-accent">
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-ink">{bedLabel(b.recording_key, b.label)}</span>
                        <StatePill state={b.decision.state} size="sm" />
                      </span>
                      <span className="flex items-end justify-between gap-2">
                        <span className="text-[22px] font-bold text-ink tnum">
                          {mgdl(b.cgm_mgdl)} <span className="text-small font-normal text-ink-3">mg/dL</span>
                        </span>
                        <Sparkline points={b.spark as [number, number][]} falling={(b.delta_2h ?? 0) < 0} />
                      </span>
                      <span className="text-[12px] text-ink-3">{b.decision.p_text ? `estimated risk ${b.decision.p_text}` : b.decision.state === "LOW_NOW" ? "observed low" : "no forecast"}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Panel>
          </>
        )}
        <Panel title="What replay is — and is not">
          <ul className="flex list-disc flex-col gap-1 pl-5 text-small text-ink-2">
            <li>Recorded development (tuning-partition) data pass through exactly the same twin, model and rules as live data would.</li>
            <li>Each recording starts at its own beginning; the clock shows time elapsed since then.</li>
            <li>The sealed evaluation patients are never offered. Replay is a demonstration, not real-time clinical monitoring.</li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}
