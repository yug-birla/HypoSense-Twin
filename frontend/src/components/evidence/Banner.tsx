"use client";
import { FlaskConical, Lock, ShieldAlert } from "lucide-react";
import type { Evidence } from "@/lib/api";

export function Banner({ ev }: { ev: Evidence }) {
  return (
    <div role="note" className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-watch-line bg-watch-tint px-5 py-3 text-watch-ink">
      <span className="inline-flex items-center gap-2 text-body font-bold uppercase tracking-wider">
        <FlaskConical aria-hidden className="size-4" /> {ev.status} evidence
      </span>
      <span className="inline-flex items-center gap-1.5 text-body">
        <Lock aria-hidden className="size-3.5" /> Evaluation partition remains sealed · confirmatory result {ev.confirmatory.split(" ")[0]}
      </span>
      <span className="inline-flex items-center gap-1.5 text-body">
        <ShieldAlert aria-hidden className="size-3.5" /> Not clinically validated
      </span>
    </div>
  );
}
