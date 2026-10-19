"use client";
// Patient twin views (redesign): profile header, status rail, the four state blocks ("worlds"),
// and the explainability view. Every value is read from the backend PatientView; missing values
// are shown as missing, never estimated in the browser.
import clsx from "clsx";
import {
  Activity,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  BellRing,
  BookOpen,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clapperboard,
  Database,
  Droplet,
  Lightbulb,
  MessageCircleQuestion,
  PillBottle,
  Utensils,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import type { PatientView } from "@/lib/api";
import { age, bedLabel, clock, mgdl, rate } from "@/lib/format";
import { useWard } from "@/lib/queries";
import { stateMeaning, stateStyle, TREND } from "@/lib/states";
import { Mascot } from "@/components/brand/Mascot";
import { Sparkline } from "@/components/ward/WardTable";
import { InfoTag, Panel, QualityBadge, StatePill } from "@/components/ui/primitives";

type Num = Record<string, number | undefined>;
type TwinData = {
  glucose?: Num;
  meals?: Num;
  medication?: Num & { quality?: Record<string, string> };
  data_quality?: { readings_last_2h?: number; expected_readings_2h?: number; conditions?: string[]; rejected_inputs?: number; halted?: boolean; sensor_day?: number };
  memory?: Num;
};
const twinOf = (v: PatientView) => (v.twin ?? {}) as TwinData;
const n = (x: number | undefined, d = 1) => (x === undefined || x === null || Number.isNaN(x) ? "—" : x.toFixed(d).replace(/\.0+$/, ""));

const CLASS_TEXT: Record<string, string> = {
  insulin: "Insulin",
  sulfonylurea: "Sulfonylurea",
  glinide: "Glinide",
  biguanide: "Metformin",
  dpp4: "DPP-4 inhibitor",
  sglt2: "SGLT2 inhibitor",
  glp1: "GLP-1 agonist",
  agi: "α-glucosidase inhibitor",
  tzd: "Thiazolidinedione",
};
const MED_Q: Record<string, string> = {
  KNOWN: "doses recorded",
  PARTIAL: "partly known",
  TIMING_UNKNOWN: "prescribed, dose times not recorded",
  DOSE_UNKNOWN: "dose unknown",
  FORMULATION_UNKNOWN: "formulation unknown",
  NO_LOGGED_MEDICATION: "none recorded",
};
const DQ: Record<string, string> = {
  AFTER_GAP: "first reading after a data gap",
  INSUFFICIENT_HISTORY: "too few recent readings",
  WARM_UP: "sensor warm-up period",
  SENSOR_FLOOR: "reading at the sensor floor",
  RAPID_CHANGE: "rapid glucose change",
  SENSOR_FAULT_SUSPECTED: "sensor fault suspected",
};

// ------------------------------------------------------------------ profile header
export function ProfileCard({ v }: { v: PatientView }) {
  const ward = useWard();
  const router = useRouter();
  const p = v.profile as Record<string, unknown>;
  const keys = (ward.data?.beds ?? []).map((b) => b.recording_key);
  const i = keys.indexOf(v.recording_key);
  const go = (k: string | undefined) => k && router.push(`/patient/?key=${encodeURIComponent(k)}`);
  const facts = [
    typeof p.sex === "string" ? (p.sex === "male" ? "Male" : "Female") : null,
    typeof p.age_y === "number" ? `${Math.round(p.age_y)} years` : null,
  ].filter(Boolean);
  const classes = ((p.prescribed_classes as string[] | undefined) ?? []).map((c) => CLASS_TEXT[c] ?? c);
  const initials = (v.label ?? v.recording_key.split("_")[0] ?? "?").slice(-2).toUpperCase();
  const s = stateStyle(v.current.state);
  return (
    <div className="card flex flex-wrap items-center gap-5 px-6 py-4">
      <span aria-hidden className={clsx("flex size-16 items-center justify-center rounded-full text-[20px] font-bold", s.pill)}>{initials}</span>
      <div className="min-w-0">
        <h1 className="text-[26px] font-bold leading-tight tracking-tight text-ink">{bedLabel(v.recording_key, v.label)}</h1>
        <p className="text-small text-ink-3">
          {facts.length ? facts.join(" · ") : "Age and sex not recorded"} · Recording {v.recording_key}
          {v.source === "NEW_DATA_SESSION" ? " · new data session" : ""}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Chip icon={<Droplet aria-hidden className="size-4 text-accent" />} top={v.source === "NEW_DATA_SESSION" ? "Diabetes type not recorded" : "Type 2 diabetes"} bottom={typeof p.diabetes_duration_y === "number" ? `${n(p.diabetes_duration_y as number, 0)} years since diagnosis` : "duration not recorded"} />
        <Chip icon={<PillBottle aria-hidden className="size-4 text-mint-ink" />} top={classes.length ? classes.slice(0, 2).join(" + ") : "Regimen not recorded"} bottom={p.treated === true ? "insulin / secretagogue" : p.treated === false ? "no insulin / secretagogue" : "prescribed regimen"} />
        <Chip icon={<CalendarDays aria-hidden className="size-4 text-sky-ink" />} top={typeof p.days_monitored === "number" ? `${n(p.days_monitored as number)} days` : "—"} bottom="monitored so far" />
      </div>
      <div className="ml-auto flex gap-2">
        <button type="button" disabled={i <= 0} onClick={() => go(keys[i - 1])} className="inline-flex h-9 items-center gap-1 rounded-full border border-line bg-surface px-3 text-small font-medium text-ink-2 disabled:opacity-40">
          <ChevronLeft aria-hidden className="size-4" /> Previous
        </button>
        <button type="button" disabled={i < 0 || i >= keys.length - 1} onClick={() => go(keys[i + 1])} className="inline-flex h-9 items-center gap-1 rounded-full border border-line bg-surface px-3 text-small font-medium text-ink-2 disabled:opacity-40">
          Next <ChevronRight aria-hidden className="size-4" />
        </button>
      </div>
    </div>
  );
}

function Chip({ icon, top, bottom }: { icon: ReactNode; top: string; bottom: string }) {
  return (
    <div className="flex items-center gap-2.5 rounded-2xl border border-line bg-surface px-3.5 py-2">
      {icon}
      <span className="leading-tight">
        <span className="block text-small font-semibold text-ink">{top}</span>
        <span className="block text-[11.5px] text-ink-3">{bottom}</span>
      </span>
    </div>
  );
}

export function BackToWard() {
  return (
    <Link href="/ward/" className="inline-flex items-center gap-1.5 text-small font-medium text-accent hover:underline">
      <ArrowLeft aria-hidden className="size-4" /> Back to ward board
    </Link>
  );
}

// ------------------------------------------------------------------ right status rail
export function StatusRail({ v, offsetS, onTab }: { v: PatientView; offsetS: number; onTab: (t: string) => void }) {
  const s = stateStyle(v.current.state);
  const m = stateMeaning(v.current.state);
  const tr = v.trend.category ? TREND[v.trend.category] : undefined;
  const lastTs = v.timeline.length ? v.timeline[v.timeline.length - 1]!.ts : null;
  const tw = twinOf(v);
  const unack = v.notifications.filter((x) => !x.acknowledged).length;
  return (
    <div className="flex flex-col gap-4">
      <section aria-label="What is happening now" className="card relative overflow-hidden p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-section font-bold text-ink">What is happening now?</p>
            <p className="text-small text-ink-3 tnum">{lastTs !== null ? `${clock(lastTs, offsetS)} record clock` : "no reading yet"}</p>
          </div>
          <StatePill state={v.current.state} size="lg" explain />
        </div>
        <div className="mt-3 flex items-end gap-4">
          <div>
            <p className="label-caps flex items-center gap-1.5">
              <span aria-hidden className="size-2 rounded-full bg-ink" /> Observed now · CGM
            </p>
            <p className={clsx("text-[44px] font-extrabold leading-none tnum", v.cgm_low ? "text-low-ink" : "text-ink")}>
              {mgdl(v.cgm_mgdl)}
              <span className="ml-1 text-body font-medium text-ink-3">mg/dL</span>
            </p>
            <p className="mt-1 text-small text-ink-2 tnum">{tr ? `${tr.glyph} ${tr.text} (${rate(v.trend.rate_mgdl_per_min)} /min)` : "trend unavailable"}</p>
            <p className={clsx("text-small tnum", v.stale ? "font-semibold text-alert-ink" : "text-ink-3")}>
              {v.stale ? "Not current — " : ""}last reading {age(v.data_age_s)}
            </p>
          </div>
          <div className="ml-auto flex items-end gap-1">
            <p className="mb-8 max-w-[150px] rounded-2xl rounded-br-sm border border-line bg-surface px-3 py-2 text-[12px] leading-4 text-ink-2 shadow-sm">
              {m.kind === "observed" ? "This is an observed reading." : m.kind === "predicted" ? "This is a forecast, not a low." : "Not enough data for a forecast."}
            </p>
            <Mascot size={66} mood={v.current.p !== null && (v.current.state === "ALERT" || v.current.state === "WATCH") ? "curious" : "calm"} />
          </div>
        </div>
        <p className="mt-2 text-small text-ink-2">{m.text}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {v.input_rejected && <QualityBadge code="INPUT_REJECTED" />}
          {v.halted && <QualityBadge code="RUNNER_HALTED" />}
          {v.data_quality.includes("SENSOR_FAULT_SUSPECTED") && <QualityBadge code="SENSOR_FAULT_SUSPECTED" />}
          {v.current.tags.map((t) => (
            <InfoTag key={t} tag={t} />
          ))}
        </div>
      </section>

      <section aria-label="Predicted risk" className={clsx("card p-5", v.current.p_text ? "bg-gradient-to-br from-white to-[#fff1f4]" : "")}>
        <p className="label-caps flex items-center gap-1.5">
          <span aria-hidden className="size-2 rounded-full border border-ink-3" /> Predicted · next 60 min
        </p>
        {v.current.p_text ? (
          <>
            <div className="mt-1 flex items-center gap-4">
              <p className={clsx("text-[44px] font-extrabold leading-none tnum", s.ink)}>{v.current.p_text}</p>
              <div className="h-2.5 flex-1 rounded-full bg-sunken">
                <div className={clsx("h-2.5 rounded-full", s.bar === "bg-transparent" ? "bg-ink-4" : s.bar)} style={{ width: `${Math.max(2, Math.min(100, (v.current.p ?? 0) * 100))}%` }} />
              </div>
            </div>
            <p className="mt-2 text-small text-ink-2">Estimated risk that a new CGM-detected low begins within 60 minutes.</p>
            <p className="text-[11.5px] font-medium text-watch-ink">{v.model_status} model · not clinically validated</p>
          </>
        ) : (
          <>
            <p className="mt-1 text-[24px] font-bold text-ink-3">No forecast</p>
            <p className="text-small text-ink-2">{v.current.texts.slice(1).join(" ") || v.current.texts[0]}</p>
          </>
        )}
      </section>

      <section aria-label="Twin summary" className="card p-5">
        <p className="text-section font-bold text-ink">Twin summary</p>
        <ul className="mt-3 flex flex-col gap-2.5">
          <World
            icon={<Droplet aria-hidden className="size-4" />}
            tone="bg-rose text-rose-ink"
            title="Glucose"
            text={tr ? `${tr.text}, ${mgdl(v.cgm_mgdl)} mg/dL` : `${mgdl(v.cgm_mgdl)} mg/dL`}
            badge={v.cgm_low ? "low now" : tw.glucose?.cgm_slope30 !== undefined && (tw.glucose.cgm_slope30 ?? 0) < -1 ? "falling" : "recorded"}
          />
          <World
            icon={<PillBottle aria-hidden className="size-4" />}
            tone="bg-mint text-mint-ink"
            title="Medication"
            text={tw.medication?.act_insulin_total ? `est. insulin activity ${n(tw.medication.act_insulin_total, 2)} IU/h` : "no estimated insulin activity"}
            badge={Object.values(tw.medication?.quality ?? {}).some((q) => q !== "KNOWN" && q !== "NO_LOGGED_MEDICATION") ? "partly known" : "estimated"}
          />
          <World
            icon={<Database aria-hidden className="size-4" />}
            tone="bg-sky text-sky-ink"
            title="Data quality"
            text={`${tw.data_quality?.readings_last_2h ?? 0} of ${tw.data_quality?.expected_readings_2h ?? 8} readings in 2 h`}
            badge={v.data_quality.length ? "check" : "sufficient"}
          />
          <World
            icon={<BookOpen aria-hidden className="size-4" />}
            tone="bg-accent-soft text-accent"
            title="Memory"
            text={`${tw.memory?.followed_by_low ?? 0} forecasts followed by a low, ${tw.memory?.not_followed_by_low ?? 0} not`}
            badge={`${unack} to acknowledge`}
          />
        </ul>
        <button type="button" onClick={() => onTab("twin")} className="mt-3 inline-flex items-center gap-1 text-small font-semibold text-accent hover:underline">
          Open twin anatomy <ArrowRight aria-hidden className="size-3.5" />
        </button>
      </section>

      <section aria-label="Actions" className="card p-5">
        <p className="text-section font-bold text-ink">Actions</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <Action primary icon={<Lightbulb aria-hidden className="size-4" />} title="Why this status?" sub="Explainability" onClick={() => onTab("explain")} />
          <Action icon={<BellRing aria-hidden className="size-4" />} title="Acknowledge alerts" sub={`${unack} waiting`} onClick={() => onTab("history")} />
          <Action icon={<MessageCircleQuestion aria-hidden className="size-4" />} title="Ask a question" sub="answers from data" onClick={() => onTab("explain")} />
          {v.source === "NEW_DATA_SESSION" ? (
            <Action icon={<Activity aria-hidden className="size-4" />} title="Add observation" sub="append to twin" onClick={() => onTab("overview")} />
          ) : (
            <Action icon={<Clapperboard aria-hidden className="size-4" />} title="Replay studio" sub="play the recording" href="/replay/" />
          )}
        </div>
      </section>
    </div>
  );
}

function World({ icon, tone, title, text, badge }: { icon: ReactNode; tone: string; title: string; text: string; badge: string }) {
  return (
    <li className="flex items-center gap-3">
      <span className={clsx("flex size-9 shrink-0 items-center justify-center rounded-xl", tone)}>{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-small font-semibold text-ink">{title}</span>
        <span className="block truncate text-[12px] text-ink-3">{text}</span>
      </span>
      <span className="shrink-0 rounded-full bg-sunken px-2 py-0.5 text-[11px] font-medium text-ink-2">{badge}</span>
    </li>
  );
}

function Action({ icon, title, sub, onClick, href, primary }: { icon: ReactNode; title: string; sub: string; onClick?: () => void; href?: string; primary?: boolean }) {
  const cls = clsx(
    "flex items-center gap-2.5 rounded-2xl border px-3 py-2.5 text-left transition-colors",
    primary ? "border-accent bg-accent text-white hover:bg-[#4f40bd]" : "border-line bg-surface text-ink hover:border-accent",
  );
  const body = (
    <>
      <span className={clsx("flex size-8 shrink-0 items-center justify-center rounded-xl", primary ? "bg-white/20" : "bg-accent-soft text-accent")}>{icon}</span>
      <span className="min-w-0 leading-tight">
        <span className="block text-small font-semibold">{title}</span>
        <span className={clsx("block text-[11px]", primary ? "text-white" : "text-ink-3")}>{sub}</span>
      </span>
    </>
  );
  return href ? (
    <Link href={href} className={cls}>
      {body}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={cls}>
      {body}
    </button>
  );
}

// ------------------------------------------------------------------ overview tab pieces
export function RecentReadings({ v, offsetS }: { v: PatientView; offsetS: number }) {
  const rows = [...v.cgm].slice(-8).reverse();
  return (
    <Panel title="Recent readings">
      {rows.length === 0 ? (
        <p className="text-small text-ink-3">No CGM reading yet.</p>
      ) : (
        <table className="w-full text-small">
          <thead>
            <tr className="text-left text-[12px] text-ink-3">
              <th className="pb-1 font-medium">Time</th>
              <th className="pb-1 text-right font-medium">CGM (mg/dL)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([t, g], i) => {
              const prev = rows[i + 1];
              const down = prev !== undefined && g < prev[1];
              return (
                <tr key={t} className="border-t border-line">
                  <td className="py-1.5 tnum text-ink-2">{clock(t, offsetS)}</td>
                  <td className={clsx("py-1.5 text-right font-semibold tnum", g < 70 ? "text-low-ink" : "text-ink")}>
                    {Math.round(g)} {prev !== undefined && <span aria-hidden className={down ? "text-alert" : "text-mint-ink"}>{down ? "↓" : g > prev[1] ? "↑" : "→"}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

export function RecentMedication({ v, offsetS }: { v: PatientView; offsetS: number }) {
  const rows = [...v.doses].slice(-6).reverse();
  return (
    <Panel title="Recorded medication (24 h)">
      {rows.length === 0 ? (
        <p className="text-small text-ink-3">No medication recorded in the last 24 hours.</p>
      ) : (
        <table className="w-full text-small">
          <thead>
            <tr className="text-left text-[12px] text-ink-3">
              <th className="pb-1 font-medium">Time</th>
              <th className="pb-1 font-medium">Medicine</th>
              <th className="pb-1 text-right font-medium">Dose</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d, i) => (
              <tr key={`${d.ts}-${i}`} className="border-t border-line">
                <td className="py-1.5 tnum text-ink-2">{clock(d.ts, offsetS)}</td>
                <td className="py-1.5 text-ink">{(d.canonical ?? "unrecognised entry").replaceAll("_", " ")}</td>
                <td className="py-1.5 text-right tnum text-ink-2">{d.dose === null ? "unknown" : `${d.dose} ${d.dose_unit ?? ""}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="mt-2 text-[11.5px] text-ink-4">As recorded. HypoSense never suggests a dose.</p>
    </Panel>
  );
}

export function DataQualityCard({ v }: { v: PatientView }) {
  const dq = twinOf(v).data_quality ?? {};
  const got = dq.readings_last_2h ?? 0;
  const exp = dq.expected_readings_2h ?? 8;
  return (
    <Panel title="Can the data be trusted right now?">
      <div className="flex items-center gap-3">
        <span className={clsx("rounded-full px-2.5 py-0.5 text-small font-semibold", v.data_quality.length ? "bg-watch-tint text-watch-ink" : "bg-mint text-mint-ink")}>
          {v.data_quality.length ? "Check" : "Sufficient"}
        </span>
        <span className="text-small text-ink-2">{v.data_quality.length ? v.data_quality.map((q) => DQ[q] ?? q).join("; ") : "enough recent CGM for a forecast"}</span>
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-xl bg-sunken p-2">
          <dt className="text-[11px] text-ink-3">Readings, last 2 h</dt>
          <dd className="text-title font-bold text-ink tnum">{got}/{exp}</dd>
        </div>
        <div className="rounded-xl bg-sunken p-2">
          <dt className="text-[11px] text-ink-3">Inputs not usable</dt>
          <dd className="text-title font-bold text-ink tnum">{v.rejected_events}</dd>
        </div>
        <div className="rounded-xl bg-sunken p-2">
          <dt className="text-[11px] text-ink-3">Processing</dt>
          <dd className="text-small font-bold text-ink">{v.halted ? "halted" : "running"}</dd>
        </div>
      </dl>
    </Panel>
  );
}

// ------------------------------------------------------------------ twin anatomy
export function TwinAnatomy({ v, offsetS }: { v: PatientView; offsetS: number }) {
  const tw = twinOf(v);
  const g = tw.glucose ?? {};
  const md = tw.medication ?? {};
  const dq = tw.data_quality ?? {};
  const mem = tw.memory ?? {};
  const meals = tw.meals ?? {};
  const tr = v.trend.category ? TREND[v.trend.category] : undefined;
  const six = v.cgm.filter(([t]) => t >= v.now_ts - 6 * 3600) as [number, number][];
  const doses = v.doses;
  const s = stateStyle(v.current.state);
  const got = dq.readings_last_2h ?? 0;
  const exp = dq.expected_readings_2h ?? 8;
  return (
    <div className="flex flex-col gap-5">
      <div className={clsx("card flex flex-wrap items-center gap-5 p-4 2xl:hidden", v.current.p_text && "bg-gradient-to-br from-white to-[#fff1f4]")}>
        <Mascot size={64} mood={v.current.p !== null && v.current.state !== "NO_ALERT" ? "curious" : "happy"} className="shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-title font-bold text-ink">HypoSense Twin</p>
          <p className="text-small text-ink-3">Combines all four blocks at every reading to estimate the risk of a low in the next 60 minutes.</p>
        </div>
        <div className="text-right">
          <p className="label-caps">Predicted risk · next 60 min</p>
          <p className={clsx("text-[30px] font-extrabold leading-tight tnum", v.current.p_text ? s.ink : "text-ink-3")}>{v.current.p_text ?? "No forecast"}</p>
          <StatePill state={v.current.state} explain />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-[minmax(0,1fr)_260px_minmax(0,1fr)]">
        <WorldCard n={1} title="Glucose World" sub="Recent CGM values, trend and variability" tone="from-[#f5f2ff] to-white" icon={<Droplet aria-hidden className="size-5" />} iconTone="bg-accent text-white">
          <div className="flex flex-col gap-3">
            <Sparkline points={six} falling={(v.trend.rate_mgdl_per_min ?? 0) < 0} width={150} height={60} />
            <dl className="grid flex-1 grid-cols-1 gap-1.5 text-small">
              <Fact k="Latest CGM" v={`${mgdl(v.cgm_mgdl)} mg/dL`} strong={v.cgm_low} />
              <Fact k="Trend (30 min)" v={tr ? `${tr.text} · ${rate(v.trend.rate_mgdl_per_min)}/min` : "—"} />
              <Fact k="Variability (SD, 2 h)" v={`${n(g.cgm_sd_2h)} mg/dL`} />
              <Fact k="Lowest in 2 h" v={`${n(g.cgm_min_2h, 0)} mg/dL`} />
            </dl>
          </div>
        </WorldCard>
        <div className="row-span-2 hidden flex-col items-center justify-center gap-3 2xl:col-start-2 2xl:row-start-1 2xl:flex">
          <div className="relative">
            <div className="absolute inset-0 -z-10 scale-[1.6] rounded-full bg-[radial-gradient(circle,#e9e3ff_0%,transparent_70%)]" />
            <Mascot size={150} mood={v.current.p !== null && v.current.state !== "NO_ALERT" ? "curious" : "happy"} />
          </div>
          <p className="text-center text-title font-bold text-ink">HypoSense Twin</p>
          <p className="text-center text-small text-ink-3">Combines all four blocks at every reading to estimate the risk of a low in the next 60 minutes.</p>
          <div className={clsx("card w-full p-4 text-center", v.current.p_text && "bg-gradient-to-br from-white to-[#fff1f4]")}>
            <p className="label-caps">Predicted risk · next 60 min</p>
            <p className={clsx("text-[38px] font-extrabold leading-tight tnum", v.current.p_text ? s.ink : "text-ink-3")}>{v.current.p_text ?? "No forecast"}</p>
            <StatePill state={v.current.state} explain />
          </div>
        </div>
        <WorldCard n={2} title="Medication World" sub="Estimated activity from recorded doses" tone="from-[#effaf5] to-white" icon={<PillBottle aria-hidden className="size-5" />} iconTone="bg-[#22a06b] text-white">
          <div className="flex flex-col gap-3">
            <DoseBars doses={doses} now={v.now_ts} />
            <dl className="grid flex-1 grid-cols-1 gap-1.5 text-small">
              <Fact k="Est. insulin activity" v={`${n(md.act_insulin_total, 2)} IU/h`} />
              <Fact k="Est. insulin on board" v={`${n(md.iob_insulin, 1)} IU`} />
              <Fact k="Est. sulfonylurea activity" v={n(md.act_su, 2)} />
              <Fact k="Since last insulin" v={md.min_since_insulin === undefined ? "none recorded" : `${n(md.min_since_insulin, 0)} min`} />
            </dl>
          </div>
          <p className="mt-2 text-[11.5px] text-ink-3">
            {Object.entries(md.quality ?? {}).map(([c, q]) => `${CLASS_TEXT[c] ?? c}: ${MED_Q[q] ?? q}`).join(" · ") || "No medication information"}. Estimates are not measured blood levels.
          </p>
        </WorldCard>
        <WorldCard n={3} title="Data Quality World" sub="Missing inputs and reliability" tone="from-[#fff8ec] to-white" icon={<Database aria-hidden className="size-5" />} iconTone="bg-[#e0a03a] text-white">
          <Bar label="CGM readings, last 2 h" value={got} max={exp} text={`${got} of ${exp}`} />
          <dl className="mt-2 grid grid-cols-1 gap-1.5 text-small">
            <Fact k="Conditions now" v={dq.conditions?.length ? dq.conditions.map((c) => DQ[c] ?? c).join(", ") : "none"} />
            <Fact k="Inputs not usable" v={String(dq.rejected_inputs ?? 0)} />
            <Fact k="Sensor day" v={dq.sensor_day === undefined ? "—" : n(dq.sensor_day, 0)} />
          </dl>
        </WorldCard>
        <WorldCard n={4} title="Memory World" sub="Past forecasts, outcomes and alerts" tone="from-[#fdf2ff] to-white" icon={<BookOpen aria-hidden className="size-5" />} iconTone="bg-[#b55bd6] text-white">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-small">
            <Fact k="Followed by a low" v={String(mem.followed_by_low ?? 0)} />
            <Fact k="Not followed" v={String(mem.not_followed_by_low ?? 0)} />
            <Fact k="Still open (60 min)" v={String(mem.forecasts_pending ?? 0)} />
            <Fact k="Outcome unknown" v={String(mem.outcome_unknown ?? 0)} />
            <Fact k="Alert notifications" v={String(mem.notifications ?? 0)} />
            <Fact k="To acknowledge" v={String(mem.unacknowledged ?? 0)} />
            <Fact k="Low episodes so far" v={String(mem.low_episodes_so_far ?? 0)} />
            <Fact k="Since last meal" v={meals.meal_min_since === undefined ? "none recorded" : `${n(meals.meal_min_since, 0)} min`} />
          </dl>
        </WorldCard>
      </div>
      <div className="card p-5">
        <p className="text-section font-bold text-ink">How the twin updates at every event</p>
        <ol className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-6">
          {[
            ["New observation arrives", Activity],
            ["Glucose World updates", Droplet],
            ["Medication World updates", PillBottle],
            ["Data Quality is checked", Database],
            ["Forecast is checked later", BookOpen],
            ["New risk and state", Lightbulb],
          ].map(([t, Icon], i) => {
            const I = Icon as typeof Activity;
            return (
              <li key={t as string} className="flex items-center gap-2 rounded-2xl border border-line bg-surface px-3 py-2.5 text-small text-ink-2">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
                  <I aria-hidden className="size-4" />
                </span>
                <span>
                  <span className="text-[10.5px] font-semibold text-ink-4">{i + 1}</span> {t as string}
                </span>
              </li>
            );
          })}
        </ol>
        <p className="mt-2 text-[11.5px] text-ink-4">
          Values are read from the twin at {clock(v.now_ts, offsetS)} (record clock) using only information available at that time. Meals and
          time of day feed the forecast too.
        </p>
      </div>
    </div>
  );
}

function WorldCard({ n: num, title, sub, tone, icon, iconTone, children }: { n: number; title: string; sub: string; tone: string; icon: ReactNode; iconTone: string; children: ReactNode }) {
  return (
    <section aria-label={title} className={clsx("card bg-gradient-to-br p-5", tone)}>
      <div className="mb-3 flex items-start gap-3">
        <span className={clsx("flex size-9 shrink-0 items-center justify-center rounded-full text-[15px] font-bold", iconTone)}>{num}</span>
        <div className="min-w-0 flex-1">
          <h3 className="text-[18px] font-bold text-ink">{title}</h3>
          <p className="text-small text-ink-3">{sub}</p>
        </div>
        <span className={clsx("flex size-11 shrink-0 items-center justify-center rounded-2xl", iconTone)}>{icon}</span>
      </div>
      <div className="rounded-2xl bg-surface/80 p-3">{children}</div>
    </section>
  );
}

function Fact({ k, v, strong }: { k: string; v: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-ink-3">{k}</dt>
      <dd className={clsx("text-right font-semibold tnum", strong ? "text-low-ink" : "text-ink")}>{v}</dd>
    </div>
  );
}

function Bar({ label, value, max, text }: { label: string; value: number; max: number; text: string }) {
  const pct = Math.max(0, Math.min(100, (100 * value) / Math.max(1, max)));
  return (
    <div>
      <div className="flex justify-between text-small">
        <span className="text-ink-3">{label}</span>
        <span className="font-semibold text-ink tnum">{text}</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-sunken">
        <div className={clsx("h-2 rounded-full", pct >= 75 ? "bg-[#22a06b]" : "bg-[#e0a03a]")} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** Recorded doses over the last 24 h as bars (insulin blue, other agents green). Recorded, not estimated. */
function DoseBars({ doses, now }: { doses: PatientView["doses"]; now: number }) {
  const w = 150;
  const h = 60;
  const recent = doses.filter((d) => d.ts >= now - 86400);
  if (!recent.length) return <span className="w-[150px] text-small text-ink-4">no doses recorded in 24 h</span>;
  const max = Math.max(1, ...recent.map((d) => d.dose ?? 1));
  return (
    <svg aria-hidden width={w} height={h}>
      <line x1={0} x2={w} y1={h - 1} y2={h - 1} stroke="#e7e4f5" />
      {recent.map((d, i) => {
        const x = ((d.ts - (now - 86400)) / 86400) * (w - 6) + 3;
        const bh = Math.max(6, ((d.dose ?? max / 3) / max) * (h - 8));
        return <rect key={i} x={x - 2.5} y={h - 1 - bh} width={5} height={bh} rx={2} fill={d.drug_class === "insulin" ? "#3b82f6" : "#22a06b"} opacity={d.dose === null ? 0.4 : 0.9} />;
      })}
    </svg>
  );
}

// ------------------------------------------------------------------ explainability
const GROUP_DETAIL: Record<string, (t: TwinData, v: PatientView) => string> = {
  G1_cgm_level: (_t, v) => `The latest CGM reading is ${mgdl(v.cgm_mgdl)} mg/dL.`,
  G2_cgm_trend: (_t, v) => `The 30-minute trend is ${rate(v.trend.rate_mgdl_per_min)} mg/dL per minute.`,
  G3_cgm_history: (t) => `Over the last 2 h the lowest reading was ${n(t.glucose?.cgm_min_2h, 0)} mg/dL (SD ${n(t.glucose?.cgm_sd_2h)}).`,
  G4_time: () => "The time of day is part of the pattern the model learned.",
  G5_static_context: () => "Recorded patient context (e.g. age, HbA1c, prescribed regimen).",
  G6_meal_timing: (t) => (t.meals?.meal_min_since === undefined ? "No meal recorded recently." : `Last recorded meal ${n(t.meals.meal_min_since, 0)} min ago.`),
  G7_raw_medication_timing: (t) => (t.medication?.min_since_insulin === undefined ? "Recorded medicine times." : `Last insulin recorded ${n(t.medication.min_since_insulin, 0)} min ago.`),
  G78_csii_iv_flags: () => "Pump or intravenous insulin information.",
  G8_medication_exposure: (t) => `Estimated insulin activity ${n(t.medication?.act_insulin_total, 2)} IU/h, insulin on board ${n(t.medication?.iob_insulin, 1)} IU.`,
};
const GROUP_PLAIN: Record<string, string> = {
  G1_cgm_level: "Current glucose level",
  G2_cgm_trend: "Recent glucose trend",
  G3_cgm_history: "Recent glucose history",
  G4_time: "Time of day",
  G5_static_context: "Patient context",
  G6_meal_timing: "Recorded meal times",
  G7_raw_medication_timing: "Recorded medicine times",
  G78_csii_iv_flags: "Pump / IV insulin",
  G8_medication_exposure: "Estimated medicine activity",
};
const GROUP_ICON: Record<string, typeof Droplet> = {
  G1_cgm_level: Droplet,
  G2_cgm_trend: ArrowDown,
  G3_cgm_history: Activity,
  G4_time: CalendarDays,
  G5_static_context: BookOpen,
  G6_meal_timing: Utensils,
  G7_raw_medication_timing: PillBottle,
  G78_csii_iv_flags: PillBottle,
  G8_medication_exposure: PillBottle,
};

export function Explainability({ v, tauAlert, tauWatch }: { v: PatientView; tauAlert?: number | null; tauWatch?: number | null }) {
  const tw = twinOf(v);
  const groups = v.contributions;
  const raises = groups.filter((g) => g.direction === "raises_risk").slice(0, 4);
  const max = Math.max(1e-9, ...groups.map((g) => Math.abs(g.contribution)));
  const [headline, ...more] = v.current.texts;
  const worried = v.current.p !== null && (v.current.state === "ALERT" || v.current.state === "WATCH");
  return (
    <div id="why" className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <section aria-label="Why is HypoSense showing this?" className="card relative overflow-hidden p-5">
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-[22px] font-bold text-ink">{worried ? "Why is the twin worried?" : "Why is HypoSense showing this?"}</h2>
            <StatePill state={v.current.state} explain />
          </div>
          <p className="mt-1 text-body text-ink-2">{headline}</p>
          {more.length > 0 && <p className="text-small text-ink-3">{more.join(" ")}</p>}
          {raises.length > 0 ? (
            <ul className="mt-4 flex flex-col gap-2.5">
              {raises.map((gr) => {
                const Icon = GROUP_ICON[gr.group] ?? Lightbulb;
                return (
                  <li key={gr.group} className="flex items-start gap-3 rounded-2xl border border-line bg-gradient-to-r from-[#fff4f7] to-white p-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-rose text-rose-ink">
                      <Icon aria-hidden className="size-4" />
                    </span>
                    <span>
                      <span className="block text-body font-semibold text-ink">{GROUP_PLAIN[gr.group] ?? gr.label}</span>
                      <span className="block text-small text-ink-3">{GROUP_DETAIL[gr.group]?.(tw, v) ?? ""}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-4 rounded-2xl bg-sunken p-3 text-small text-ink-3">
              {v.current.p === null ? "There is no estimate in this state, so nothing is attributed." : "No information group pushes this estimate up."}
            </p>
          )}
          <p className="mt-3 text-[12px] text-ink-3">These are statistical associations with this estimate — not causes, and never a reason to change treatment.</p>
        </section>
        <Panel title="Information associated with this estimate" aside={<span className="text-[11px] text-ink-4">grouped TreeSHAP · raw score</span>}>
          {groups.length === 0 ? (
            <p className="text-small text-ink-3">No attribution: there is no current forecast.</p>
          ) : (
            <ul aria-label="Factor groups" className="flex flex-col gap-2">
              {groups.map((gr) => (
                <li key={gr.group} className="grid grid-cols-[150px_1fr_52px] items-center gap-2 text-small">
                  <span className="truncate text-ink-2">{GROUP_PLAIN[gr.group] ?? gr.label}</span>
                  <span className="relative h-3 rounded-full bg-sunken">
                    <span aria-hidden className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                    <span
                      className={clsx("absolute inset-y-0 rounded-full", gr.direction === "raises_risk" ? "left-1/2 bg-[#e0457b]" : "right-1/2 bg-[#8b7cf6]")}
                      style={{ width: `${(50 * Math.abs(gr.contribution)) / max}%` }}
                    />
                  </span>
                  <span className={clsx("flex items-center justify-end gap-0.5 text-right font-semibold tnum", gr.direction === "raises_risk" ? "text-rose-ink" : "text-accent")}>
                    {gr.direction === "raises_risk" ? <ArrowUp aria-label="pushes the estimate up" className="size-3" /> : <ArrowDown aria-label="pushes the estimate down" className="size-3" />}
                    {Math.abs(gr.contribution).toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[11.5px] text-ink-4">
            Contribution to the model’s raw score (log-odds) before calibration, summed per group. Left: pushes the estimate down; right: up.
          </p>
        </Panel>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel title="Key values in the twin now">
          <dl className="grid grid-cols-1 gap-1.5 text-small sm:grid-cols-2 sm:gap-x-6">
            <Fact k="Current glucose" v={`${mgdl(v.cgm_mgdl)} mg/dL`} strong={v.cgm_low} />
            <Fact k="30-min trend" v={`${rate(v.trend.rate_mgdl_per_min)} mg/dL/min`} />
            <Fact k="Variability (SD, 2 h)" v={`${n(tw.glucose?.cgm_sd_2h)} mg/dL`} />
            <Fact k="Lowest in 2 h" v={`${n(tw.glucose?.cgm_min_2h, 0)} mg/dL`} />
            <Fact k="Est. insulin activity" v={`${n(tw.medication?.act_insulin_total, 2)} IU/h`} />
            <Fact k="Since last insulin" v={tw.medication?.min_since_insulin === undefined ? "none recorded" : `${n(tw.medication.min_since_insulin, 0)} min`} />
            <Fact k="Since last meal" v={tw.meals?.meal_min_since === undefined ? "none recorded" : `${n(tw.meals.meal_min_since, 0)} min`} />
            <Fact k="Low episodes so far" v={String(tw.memory?.low_episodes_so_far ?? 0)} />
          </dl>
          <details className="mt-3 rounded-xl border border-line bg-sunken px-3 py-2 text-small">
            <summary className="cursor-pointer font-medium text-ink-2">Technical detail</summary>
            <dl className="mt-2 grid grid-cols-1 gap-1">
              <Fact k="Policy state" v={v.current.state} />
              <Fact k="Calibrated probability" v={v.current.p === null ? "—" : `${(v.current.p * 100).toFixed(2)} %`} />
              <Fact k="Alert threshold (τA)" v={tauAlert == null ? "—" : `${(tauAlert * 100).toFixed(2)} %`} />
              <Fact k="Watch threshold (τW)" v={tauWatch == null ? "—" : `${(tauWatch * 100).toFixed(2)} %`} />
              <Fact k="Reason codes" v={v.current.reasons.join(", ") || "—"} />
              <Fact k="Decision" v={v.current.decision_id ?? "—"} />
            </dl>
            <p className="mt-2 text-[11px] text-ink-3">Thresholds are frozen in the model artefact; the policy (not the model) turns the probability into a state.</p>
          </details>
        </Panel>
        <section aria-label="Important notes" className="card bg-gradient-to-br from-[#f5f2ff] to-white p-5">
          <p className="flex items-center gap-2 text-section font-bold text-ink">
            <Lightbulb aria-hidden className="size-5 text-accent" /> Important notes
          </p>
          <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-small text-ink-2">
            <li>These explanations show learned associations, not proven causes.</li>
            <li>Information is grouped (glucose, medicines, meals, context) so it can be read at a glance.</li>
            <li>“What if” scenarios are deliberately not offered: changing a dose in a model is not evidence about a patient, and HypoSense never suggests doses.</li>
            <li>This is a research prototype, not a medical device.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
