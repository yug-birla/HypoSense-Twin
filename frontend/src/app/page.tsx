"use client";
// Welcome: what HypoSense is, the four state blocks of the twin, what each state means, where to
// start. Every statement describes implemented behaviour (state engine, policy, replay, intake).
import clsx from "clsx";
import { ArrowRight, BookOpen, Database, Droplet, FlaskConical, History, PillBottle, PlayCircle, Search, ShieldAlert, ShieldCheck, Sigma, Waypoints, Ban, TrendingUp, ClipboardCheck } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { useConfirmatory, useMeta } from "@/lib/queries";
import { STATE_MEANING, type PolicyState } from "@/lib/states";
import { Mascot } from "@/components/brand/Mascot";
import { StatePill } from "@/components/ui/primitives";

const WORLDS = [
  { icon: Droplet, title: "Glucose World", text: "CGM level, trend and variability", tone: "bg-rose text-rose-ink", pos: "left-0 top-6" },
  { icon: PillBottle, title: "Medication World", text: "Recorded doses → estimated activity", tone: "bg-mint text-mint-ink", pos: "left-2 top-[190px]" },
  { icon: Database, title: "Data Quality World", text: "Gaps, warm-up, sensor checks", tone: "bg-sky text-sky-ink", pos: "right-0 top-2" },
  { icon: BookOpen, title: "Forecast Memory", text: "Past forecasts and what followed", tone: "bg-accent-soft text-accent", pos: "right-2 top-[200px]" },
];

const STEPS: { icon: typeof Search; title: string; text: string; tone: string }[] = [
  { icon: Search, title: "Observe", text: "Replay recorded CGM, meals and medication as if they were arriving live.", tone: "bg-accent-soft text-accent" },
  { icon: TrendingUp, title: "Forecast", text: "See the model-estimated risk that a CGM-detected low begins within 60 minutes.", tone: "bg-mint text-mint-ink" },
  { icon: ClipboardCheck, title: "Review", text: "Read why, check data quality, acknowledge alerts and see what happened afterwards.", tone: "bg-peach text-peach-ink" },
];

const FLOW = [
  { icon: Database, title: "Patient data", text: "CGM readings, recorded medicines and meals, and available patient context." },
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

function Trust({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return (
    <div className="flex items-start gap-3 px-4 py-3">
      <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">{icon}</span>
      <span>
        <span className="block text-small font-semibold text-ink">{title}</span>
        <span className="block text-[12px] leading-4 text-ink-3">{text}</span>
      </span>
    </div>
  );
}

export default function OverviewPage() {
  const meta = useMeta();
  const conf = useConfirmatory();
  return (
    <div className="flex flex-col gap-8 px-6 py-6">
      <section className="card hero-grad relative grid grid-cols-1 gap-8 overflow-hidden px-8 py-8 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="relative z-10 flex flex-col gap-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.25em] text-ink-3">Research prototype · not clinically validated</p>
          <h1 className="text-[44px] font-extrabold leading-[1.05] tracking-tight text-ink">
            Welcome to{" "}
            <span className="bg-gradient-to-r from-[#5f4fd1] to-[#8b5cf6] bg-clip-text text-transparent">HypoSense Twin</span>
          </h1>
          <p className="max-w-2xl text-[17px] leading-relaxed text-ink-2">
            An early-warning digital twin for <strong className="font-semibold text-ink">low glucose</strong>. It combines continuous glucose
            monitor (CGM) readings, recorded medication and patient context to estimate whether a new CGM-detected low-glucose episode may
            begin <strong className="font-semibold text-ink">within the next hour</strong> — so staff can check the patient earlier.
          </p>
          <p className="max-w-2xl text-small text-ink-3">
            Forecasts come from a <span className="font-medium text-ink-2">{meta.data?.model_status ?? "DEVELOPMENT"}</span> model; the final
            sealed evaluation is <span className="font-medium text-ink-2">{conf.data?.status ?? "PENDING"}</span>.
          </p>
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {STEPS.map(({ icon: Icon, title, text, tone }) => (
              <li key={title} className="card flex flex-col gap-2 p-4">
                <span className={clsx("flex size-11 items-center justify-center rounded-2xl", tone)}>
                  <Icon aria-hidden className="size-5" />
                </span>
                <span className="text-[16px] font-semibold text-ink">{title}</span>
                <span className="text-small text-ink-3">{text}</span>
              </li>
            ))}
          </ul>
          <div aria-label="Where to start" className="flex flex-wrap gap-3">
            <Link href="/demo/" className="inline-flex h-12 items-center gap-2 rounded-full bg-accent px-6 text-[15px] font-semibold text-white shadow-[0_8px_20px_rgba(95,79,209,0.32)] hover:bg-[#4f40bd]">
              <PlayCircle aria-hidden className="size-5" /> Guided demo (5 min)
            </Link>
            <Link href="/ward/" className="inline-flex h-12 items-center gap-2 rounded-full border border-line-strong bg-surface px-6 text-[15px] font-semibold text-ink hover:border-accent">
              Explore the ward replay <ArrowRight aria-hidden className="size-4" />
            </Link>
            <Link href="/intake/" className="inline-flex h-12 items-center gap-2 rounded-full border border-line-strong bg-surface px-6 text-[15px] font-semibold text-ink hover:border-accent">
              Add patient data <ArrowRight aria-hidden className="size-4" />
            </Link>
          </div>
          <div className="card grid grid-cols-1 divide-y divide-line sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            <Trust icon={<Database aria-hidden className="size-4" />} title="Retrospective replay" text="Recorded data only; not real-time monitoring." />
            <Trust icon={<ShieldCheck aria-hidden className="size-4" />} title="Research prototype" text="For research; not a medical device." />
            <Trust icon={<Ban aria-hidden className="size-4" />} title="Never recommends doses" text="No treatment or dosing advice, ever." />
          </div>
        </div>
        <div aria-label="The four parts of the twin" className="relative hidden min-h-[400px] xl:block">
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
            <div className="absolute inset-0 -z-10 scale-150 rounded-full bg-[radial-gradient(circle,#e9e3ff_0%,transparent_70%)]" />
            <Mascot size={220} />
          </div>
          {WORLDS.map(({ icon: Icon, title, text, tone, pos }) => (
            <div key={title} className={clsx("card absolute flex w-[210px] items-center gap-3 p-3", pos)}>
              <span className={clsx("flex size-11 shrink-0 items-center justify-center rounded-2xl", tone)}>
                <Icon aria-hidden className="size-5" />
              </span>
              <span>
                <span className="block text-small font-semibold text-ink">{title}</span>
                <span className="block text-[11.5px] leading-4 text-ink-3">{text}</span>
              </span>
            </div>
          ))}
        </div>
      </section>

      <section aria-labelledby="how" className="flex flex-col gap-3">
        <h2 id="how" className="text-[20px] font-bold text-ink">How the twin works</h2>
        <ol className="grid grid-cols-1 gap-3 md:grid-cols-5">
          {FLOW.map(({ icon: Icon, title, text }, i) => (
            <li key={title} className="card relative flex flex-col gap-1.5 p-4">
              <span className="flex items-center gap-2 text-body font-semibold text-ink">
                <span aria-hidden className="flex size-7 items-center justify-center rounded-full bg-accent text-[12px] font-bold text-white">{i + 1}</span>
                <Icon aria-hidden className="size-4 text-accent" />
                {title}
              </span>
              <span className="text-small text-ink-2">{text}</span>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="states" className="flex flex-col gap-3">
        <h2 id="states" className="text-[20px] font-bold text-ink">What the states mean</h2>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          {GROUPS.map((g) => (
            <div key={g.title} className="card flex flex-col gap-3 p-5">
              <div>
                <p className="text-section font-semibold text-ink">{g.title}</p>
                <p className="text-[12px] text-ink-3">{g.note}</p>
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
        <Link href="/evidence/" className="card flex items-start gap-3 p-5 hover:border-accent">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-accent-soft text-accent">
            <FlaskConical aria-hidden className="size-5" />
          </span>
          <span>
            <span className="block text-section font-semibold text-ink">How was it tested?</span>
            <span className="text-small text-ink-3">Plain-language evidence first, every technical detail one click further.</span>
          </span>
        </Link>
        <div className="card flex items-start gap-3 p-5">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-mint text-mint-ink">
            <BookOpen aria-hidden className="size-5" />
          </span>
          <span className="text-small text-ink-2">
            <span className="block text-section font-semibold text-ink">The scientific question</span>
            Does knowing when medicines were given (estimated medicine activity) improve early warning beyond a strong glucose-and-context
            model? The answer is decided only by a sealed, pre-registered evaluation that has not been run yet.
          </span>
        </div>
      </section>
    </div>
  );
}
