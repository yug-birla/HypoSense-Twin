"use client";
// "Understand the evidence": plain-language summary of the SAME canonical numbers shown in the
// technical section below (read from the evidence endpoint; nothing computed beyond formatting).
import type { ReactNode } from "react";
import type { Evidence } from "@/lib/api";
import { pct } from "@/lib/format";
import { Details, Panel } from "@/components/ui/primitives";

function QA({ q, children }: { q: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-line p-4">
      <h3 className="text-body font-semibold text-ink">{q}</h3>
      <div className="text-small leading-relaxed text-ink-2">{children}</div>
    </div>
  );
}

const pp = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)} percentage points`);

export function PlainEvidence({ ev, confirmatory }: { ev: Evidence; confirmatory: string }) {
  const lad = ev.ladder.treated;
  const m = lad?.models ?? {};
  const s = (k: string) => m[k]?.sens_at_1fa;
  const ci = (k: string) => m[k]?.sens_at_1fa_ci95;
  const c = ev.comparisons["preview_M3-M2:sens1"];
  const ciText = (v: number[] | null | undefined) => (v ? `${pct(v[0])} to ${pct(v[1])}` : "");
  return (
    <Panel title="Understand the evidence" aside={<span className="text-[11px] text-ink-4">plain-language summary of the numbers below</span>}>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
        <QA q="What are we trying to predict?">
          Whether a new low-glucose episode detected by the CGM (below 70 mg/dL) will begin within the next{" "}
          {ev.task.horizon_min} minutes. A warning counts only if it comes 15–60 minutes before the low starts.
        </QA>
        <QA q="How was it tested?">
          Patients were split once, before any modelling, into a development group and a sealed evaluation group. All
          development results here come from the development group only, using cross-validation in which a patient is never
          used to train the model that is tested on them.
        </QA>
        <QA q="What is being compared?">
          A ladder of models: a simple glucose-trend rule (M0), glucose-only learning (M1), plus patient context and meals (M2), plus
          recorded medicine times (M3r), and plus estimated medicine activity (M3). The key question is M3 versus M2.
        </QA>
        <QA q="What do the development results suggest?">
          At one false alert per patient-day, the models warned in time for {pct(s("M2"))} (M2) and {pct(s("M3"))} (M3) of{" "}
          {lad?.episodes ?? "the"} low episodes in {lad?.patients ?? "the"} treated development patients. The difference M3 − M2 is{" "}
          {pp(c?.point)}, but its 95% interval ({c?.ci95 ? `${(c.ci95[0]! * 100).toFixed(1)} to ${(c.ci95[1]! * 100).toFixed(1)}` : "—"}{" "}
          points) includes zero: <b className="font-semibold text-ink">no reliable difference yet</b>.
        </QA>
        <QA q="What are the limitations?">
          One dataset from one centre; small numbers of patients and episodes, so wide uncertainty; lows are CGM-detected (capillary
          glucose often disagrees); medicine activity is estimated with fixed population profiles not yet reviewed by a pharmacist;
          no clinical-outcome evaluation.
        </QA>
        <QA q="Is the final evaluation complete?">
          <b className="font-semibold text-ink">No — {confirmatory.split(" ")[0]}.</b> The sealed evaluation group has never been
          opened. It will be evaluated once, with every rule frozen in advance; until then all numbers are development evidence.
        </QA>
      </div>
      <div className="mt-3">
        <Details summary="What the metrics mean">
          <dl className="flex flex-col gap-2">
            <div>
              <dt className="font-semibold text-ink">Sensitivity (episode-level)</dt>
              <dd>Of the eligible CGM-detected low episodes, the fraction that received a notification 15–60 minutes before onset.</dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">False alerts per patient-day (FA/day)</dt>
              <dd>
                Notifications not followed by a qualifying episode onset, divided by monitored patient-days. “Sensitivity at 1 FA/day” is
                read from each model’s operating curve at that budget; it is an evaluation operating point, not a promise of exactly
                one false alert per day.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">95% confidence interval</dt>
              <dd>
                The range of plausible values under the study’s resampling procedure (patients resampled with replacement, 2,000 times).
                If the interval of a difference includes zero, the data do not show a reliable difference.
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">Calibration</dt>
              <dd>How closely the estimated probabilities match how often lows actually followed (e.g. of forecasts near 10%, about 10% followed by a low).</dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">Model ladder (technical)</dt>
              <dd>
                M2: {pct(s("M2"))} ({ciText(ci("M2"))}); M3: {pct(s("M3"))} ({ciText(ci("M3"))}). Full table, curves and paired comparisons
                below.
              </dd>
            </div>
          </dl>
        </Details>
      </div>
    </Panel>
  );
}
