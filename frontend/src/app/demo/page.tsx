"use client";
import { PlayCircle } from "lucide-react";
import { PageHeader } from "@/components/shell/AppShell";
import { Button, Panel } from "@/components/ui/primitives";
import { STEPS, useDemo } from "@/lib/demo";

export default function DemoPage() {
  const d = useDemo();
  return (
    <div>
      <PageHeader title="Guided demo" sub="About 5 minutes. Drives the real replay — nothing is simulated or staged." />
      <div className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
        <Panel>
          <ol className="flex flex-col gap-3">
            {STEPS.map((s, i) => (
              <li key={s.title} className="flex gap-3">
                <span aria-hidden className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[12px] font-semibold text-accent">
                  {i + 1}
                </span>
                <span>
                  <span className="block text-body font-semibold text-ink">{s.title}</span>
                  <span className="text-small text-ink-3">{s.body}</span>
                </span>
              </li>
            ))}
          </ol>
          <Button variant="primary" className="mt-5" onClick={d.start}>
            <PlayCircle aria-hidden className="size-4" /> {d.active ? "Restart the guided demo" : "Start the guided demo"}
          </Button>
          <p className="mt-3 text-[11.5px] text-ink-4">
            Starting the demo replaces any running ward replay with the 8 default recordings. New-data sessions are not affected. The
            guide stays in the corner while you move between pages; close it at any time.
          </p>
        </Panel>
      </div>
    </div>
  );
}
