"use client";
// Overview: what HypoSense is, how the twin works, what each state means, where to start.
// Every statement describes implemented behaviour (policy/decide.py, replay, intake, evidence).
import { ArrowRight, BookOpenCheck, Database, FlaskConical, History, LayoutList, PlayCircle, ShieldAlert, Sigma, UserPlus, Waypoints } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { useConfirmatory, useMeta } from "@/lib/queries";
import { STATE_MEANING, type PolicyState } from "@/lib/states";
import { StatePill } from "@/components/ui/primitives";

function Start({ href, icon, title, text, primary }: { href: string; icon: ReactNode; title: string; text: string; primary?: boolean }) {
  return (
    <Link
      href={href}
      className={
        primary
          ? "group flex flex-col gap-2 rounded-lg border border-ink bg-ink p-5 text-white transition-colors hover:bg-ink-2"
          : "group flex flex-col gap-2 rounded-lg border border-line bg-surface p-5 transition-colors hover:border-accent"
      }
    >
      <span className="flex items-center gap-2 text-[15px] font-semibold">
        {icon}
        {title}
        <ArrowRight aria-hidden className="ml-auto size-4 opacity-60 transition-transform group-hover:translate-x-0.5" />
      </span>
      <span className={primary ? "text-small text-white/80" : "text-small text-ink-3"}>{text}</span>
    </Link>
  );
}

const FLOW = [
  { icon: Database, title: "Patient data", text: "CGM glucose readings, recorded medicines and meals, and available patient context." },
  { icon: Waypoints, title: "Digital twin", text: "Keeps an up-to-date picture of the patient: recent glucose, estimated medicine activity and data quality." },
  { icon: Sigma, title: "Risk estimate", text: "Estimates the risk that a new CGM-detected low (< 70 mg/dL) begins within the next 60 minutes." },
  { icon: ShieldAlert, title: "Alert rules", text: "Fixed rules turn the estimate into a state — ALERT, WATCH, no alert — or explain why no forecast is possible." },
  { icon: History, title: "History", text: "Every forecast is later checked against what the CGM actually showed in the next 60 minutes." },
];

const GROUPS: { title: string; note: string; states: PolicyState[] }[] = [
  { title: "Observed now", note: "Based on the CGM reading itself", states: ["LOW_NOW"] },
  { title: "Prediction for the next 60 minutes", note: "Model estimate — not a confirmed low", states: ["ALERT", "WATCH", "NO_ALERT"] },
  { title: "No forecast available", note: "Low risk and missing information are never confused", states: ["INSUFFICIENT_DATA", "SYSTEM_ERROR"] },
];

export default function OverviewPage() {
  const meta = useMeta();
  const conf = useConfirmatory();
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-8 px-6 py-8">
      <section className="flex flex-col gap-3">
        <p className="label-caps text-accent">Research prototype · not clinically validated</p>
        <h1 className="text-[28px] font-semibold leading-tight tracking-tight text-ink">HypoSense Twin</h1>
        <p className="max-w-3xl text-[17px] leading-relaxed text-ink-2">
          An early-warning digital twin for <strong className="font-semibold text-ink">low glucose</strong>. It combines continuous glucose
          monitor (CGM) readings, recorded medication and patient context to estimate whether a new CGM-detected low-glucose episode may
          begin <strong className="font-semibold text-ink">within the next hour</strong> — so staff can check the patient earlier.
        </p>
        <p className="max-w-3xl text-small text-ink-3">
          Not a medical device. It never recommends doses or treatment; the only supported action is human review and capillary
          confirmation. Forecasts come from a{" "}
          <span className="font-medium text-ink-2">{meta.data?.model_status ?? "DEVELOPMENT"}</span> model; the final sealed evaluation is{" "}
          <span className="font-medium text-ink-2">{conf.data?.status ?? "PENDING"}</span>.
        </p>
      </section>

      <section aria-label="Where to start" className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Start primary href="/demo/" icon={<PlayCircle aria-hidden className="size-5" />} title="Guided demo (5 min)" text="A step-by-step tour of a real recorded case: readings arrive, the twin updates, an alert appears and we check what happened." />
        <Start href="/ward/" icon={<LayoutList aria-hidden className="size-5" />} title="Explore the ward replay" text="Replay recorded patients from the development data and see who needs attention, minute by minute." />
        <Start href="/intake/" icon={<UserPlus aria-hidden className="size-5" />} title="Add patient data" text="Upload a CGM file or enter readings; HypoSense asks only what it needs and builds a live twin." />
      </section>

      <section aria-labelledby="how" className="flex flex-col gap-3">
        <h2 id="how" className="text-[17px] font-semibold text-ink">How the twin works</h2>
        <ol className="grid grid-cols-1 gap-2 md:grid-cols-5">
          {FLOW.map(({ icon: Icon, title, text }, i) => (
            <li key={title} className="relative flex flex-col gap-1.5 rounded-lg border border-line bg-surface p-4">
              <span className="flex items-center gap-2 text-body font-semibold text-ink">
                <span aria-hidden className="flex size-6 items-center justify-center rounded-full bg-accent-soft text-[12px] font-semibold text-accent">{i + 1}</span>
                <Icon aria-hidden className="size-4 text-ink-3" />
                {title}
              </span>
              <span className="text-small text-ink-2">{text}</span>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="states" className="flex flex-col gap-3">
        <h2 id="states" className="text-[17px] font-semibold text-ink">What the states mean</h2>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          {GROUPS.map((g) => (
            <div key={g.title} className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4">
              <div>
                <p className="text-body font-semibold text-ink">{g.title}</p>
                <p className="text-[11.5px] text-ink-3">{g.note}</p>
              </div>
              <ul className="flex flex-col gap-3">
                {g.states.map((s) => (
                  <li key={s} className="flex flex-col items-start gap-1">
                    <StatePill state={s} size="sm" />
                    <span className="text-small text-ink-2">{STATE_MEANING[s].text}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Link href="/evidence/" className="flex items-start gap-3 rounded-lg border border-line bg-surface p-4 hover:border-accent">
          <FlaskConical aria-hidden className="mt-0.5 size-5 text-ink-3" />
          <span>
            <span className="block text-body font-semibold text-ink">How was it tested?</span>
            <span className="text-small text-ink-3">Plain-language evidence first, every technical detail one click further.</span>
          </span>
        </Link>
        <div className="flex items-start gap-3 rounded-lg border border-line bg-surface p-4">
          <BookOpenCheck aria-hidden className="mt-0.5 size-5 text-ink-3" />
          <span className="text-small text-ink-2">
            <span className="block text-body font-semibold text-ink">The scientific question</span>
            Does knowing when medicines were given (estimated medicine activity) improve early warning beyond a strong glucose-and-context
            model? The answer is decided only by a sealed, pre-registered evaluation that has not been run yet.
          </span>
        </div>
      </section>
    </div>
  );
}
