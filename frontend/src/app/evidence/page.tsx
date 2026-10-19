"use client";
import clsx from "clsx";
import { Activity, Gauge, Lightbulb, Lock, Target } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { Evidence } from "@/lib/api";
import { num, pct, shortHash } from "@/lib/format";
import { useEvidence } from "@/lib/queries";
import { PageHeader } from "@/components/shell/AppShell";
import { Banner } from "@/components/evidence/Banner";
import { ConfirmatoryPanel } from "@/components/evidence/Confirmatory";
import { PlainEvidence } from "@/components/evidence/PlainEvidence";
import { FrocChart, IntervalBar, MODEL_COLOR, MODEL_DESC, MODEL_ORDER, ReliabilityChart } from "@/components/evidence/EvidenceCharts";
import { ErrorBox, KV, Panel, Skeleton, StatusTag } from "@/components/ui/primitives";

type Pop = "treated" | "all";

function PopSwitch({ pop, setPop }: { pop: Pop; setPop: (p: Pop) => void }) {
  return (
    <div role="radiogroup" aria-label="Population" className="inline-flex rounded-full border border-line-strong bg-surface p-1">
      {(["treated", "all"] as const).map((p) => (
        <button
          key={p}
          role="radio"
          aria-checked={pop === p}
          type="button"
          onClick={() => setPop(p)}
          className={clsx("h-8 rounded-full px-3.5 text-small font-medium", pop === p ? "bg-accent text-white" : "text-ink-2 hover:bg-sunken")}
        >
          {p === "treated" ? "Treated patients" : "All patients"}
        </button>
      ))}
    </div>
  );
}

function Ladder({ ev, pop }: { ev: Evidence; pop: Pop }) {
  const lp = ev.ladder[pop];
  if (!lp) return null;
  return (
    <table className="w-full text-small">
      <thead>
        <tr className="border-b border-line bg-sunken text-left">
          {["Model", "Inputs", "Sensitivity @ 1 FA/day (95% CI)", "", "Partial area 0.5–2 FA", "Alert precision", "Median lead", "Log-loss", "ECE"].map((h, i) => (
            <th key={i} scope="col" className={clsx("label-caps px-3 py-2", i >= 4 && "text-right")}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {MODEL_ORDER.filter((m) => lp.models[m]).map((m) => {
          const x = lp.models[m]!;
          const op = x.operating_point;
          return (
            <tr key={m} className={clsx("border-b border-line last:border-b-0", m === "M3" && "bg-accent-soft/40")}>
              <th scope="row" className="px-3 py-2 text-left">
                <span className="inline-flex items-center gap-2 font-semibold text-ink">
                  <span aria-hidden className="size-2 rounded-full" style={{ background: MODEL_COLOR[m] }} />
                  {m}
                </span>
              </th>
              <td className="px-3 py-2 text-ink-3">{MODEL_DESC[m]}</td>
              <td className="px-3 py-2 tnum">
                <span className="font-semibold text-ink">{pct(x.sens_at_1fa)}</span>
                <span className="ml-1.5 text-ink-3">
                  {x.sens_at_1fa_ci95 ? `${pct(x.sens_at_1fa_ci95[0])}–${pct(x.sens_at_1fa_ci95[1])}` : ""}
                </span>
              </td>
              <td className="px-3 py-2">
                <IntervalBar point={x.sens_at_1fa} ci={x.sens_at_1fa_ci95} lo={0.4} hi={1} color={MODEL_COLOR[m]} />
              </td>
              <td className="px-3 py-2 text-right tnum">{num(x.partial_area, 3)}</td>
              <td className="px-3 py-2 text-right tnum">{pct(op?.alert_precision)}</td>
              <td className="px-3 py-2 text-right tnum">{op?.lead_min?.median !== undefined && op?.lead_min?.median !== null ? `${op.lead_min.median} min` : "—"}</td>
              <td className="px-3 py-2 text-right tnum">{num(x.log_loss, 4)}</td>
              <td className="px-3 py-2 text-right tnum">{num(x.calibration?.ece, 4)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const COMPARISONS: Array<[string, string]> = [
  ["C0_M1-M0:sens1", "C0 · M1 − M0 (learning vs trend rule)*"],
  ["C1_M2-M1:sens1", "C1 · M2 − M1 (context and meals)"],
  ["C2a_M3r-M2:sens1", "C2a · M3r − M2 (raw medication timing)"],
  ["C2b_M3-M3r:sens1", "C2b · M3 − M3r (exposure representation)"],
  ["preview_M3-M2:sens1", "M3 − M2 (primary contrast; development preview)"],
];

function Comparisons({ ev }: { ev: Evidence }) {
  return (
    <div>
      <ul className="flex flex-col divide-y divide-line">
        {COMPARISONS.filter(([k]) => ev.comparisons[k]).map(([k, label]) => {
          const c = ev.comparisons[k]!;
          const excl = c.excludes_zero === true;
          return (
            <li key={k} className="grid grid-cols-[minmax(0,1fr)_170px_150px] items-center gap-3 py-2">
              <span className="text-body text-ink-2">{label}</span>
              <IntervalBar point={c.point} ci={c.ci95} lo={-0.2} hi={0.5} zero color={excl ? "#5f4fd1" : "#8d96a5"} />
              <span className="text-right text-small tnum">
                <span className="font-semibold text-ink">{c.point !== null && c.point !== undefined ? `${c.point > 0 ? "+" : ""}${(c.point * 100).toFixed(1)} pp` : "—"}</span>
                <span className="ml-1 text-ink-3">
                  {c.ci95 ? `(${(c.ci95[0]! * 100).toFixed(1)} to ${(c.ci95[1]! * 100).toFixed(1)})` : ""}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-[11.5px] text-ink-3">
        Paired patient-cluster bootstrap (2,000 resamples), treated patients, development data. Grey = interval includes 0.
        <br />* M0 (pre-specified trend baseline) is a weak reference: the post-hoc CGM-level reference matches the
        learned models on T (see below).
      </p>
    </div>
  );
}

function Gates({ ev }: { ev: Evidence }) {
  return (
    <ul className="flex flex-col gap-2">
      {ev.gates.map((g) => (
        <li key={g.gate ?? g.title} className="rounded-md border border-line px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-body font-medium text-ink">
              {g.gate} · {g.title}
            </span>
            <StatusTag tone={g.status === "PASS" ? "ok" : "warn"}>{g.status}</StatusTag>
          </div>
          {g.status !== "PASS" && g.summary.map((s) => <p key={s} className="mt-1 text-small text-ink-2">{s}</p>)}
        </li>
      ))}
    </ul>
  );
}

const TABS = [
  ["overview", "Overview"],
  ["models", "Model comparison"],
  ["calibration", "Calibration"],
  ["confirmatory", "Confirmatory test"],
  ["data", "Data & safeguards"],
  ["provenance", "Provenance"],
] as const;

function Kpi({ icon, label, value, sub, tone }: { icon: ReactNode; label: string; value: ReactNode; sub: string; tone: string }) {
  return (
    <div className="card flex items-center gap-4 px-5 py-4">
      <span className={clsx("flex size-12 shrink-0 items-center justify-center rounded-2xl", tone)}>{icon}</span>
      <span className="min-w-0">
        <span className="block text-small text-ink-3">{label}</span>
        <span className="block text-[22px] font-bold leading-tight text-ink">{value}</span>
        <span className="block text-[12px] text-ink-3">{sub}</span>
      </span>
    </div>
  );
}

const DATASET: [string, string, string][] = [
  ["ShanghaiT2DM (Zhao et al., 2023)", "CC BY 4.0 · public, de-identified", "data/README.md"],
  ["100 patients · 109 recordings", "type 2 diabetes · 15-min CGM", "audit G0"],
  ["112,475 CGM time points", "13 without a value (device change)", "artifacts/gates/G0.json"],
  ["348 CGM-detected L1 episodes", "107,210 prediction times", "S2 labels"],
  ["Development: 30 patients", "22 treated · nested patient-grouped CV", "partition"],
  ["Sealed evaluation: 70 patients", "50 treated · never opened", "partition"],
];

export default function EvidencePage() {
  const q = useEvidence();
  const [pop, setPop] = useState<Pop>("treated");
  const [calModel, setCalModel] = useState("M3");
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("overview");
  const lad = q.data?.ladder[pop];
  const d = q.data?.comparisons["preview_M3-M2:sens1"];
  return (
    <div>
      <PageHeader
        title="Evidence garden"
        sub="How HypoSense was tested, what the development results suggest, and what is still unknown. Every number comes from versioned run records."
        bubble="Transparent results, reproducible analysis — including the negative ones."
        mood="curious"
        aside={q.data && <PopSwitch pop={pop} setPop={setPop} />}
      />
      <div className="flex flex-col gap-4 p-6">
        {q.isError && <ErrorBox title="Evidence unavailable" detail={(q.error as Error).message} onRetry={() => q.refetch()} />}
        {!q.data && !q.isError && <Skeleton className="h-96 w-full" />}
        {q.data && (
          <>
            <Banner ev={q.data} />
            <div role="tablist" aria-label="Evidence views" className="flex flex-wrap gap-2">
              {TABS.map(([id, label]) => (
                <button
                  key={id}
                  role="tab"
                  type="button"
                  aria-selected={tab === id}
                  onClick={() => setTab(id)}
                  className={clsx(
                    "h-10 rounded-full px-5 text-body font-medium transition-colors",
                    tab === id ? "bg-accent text-white shadow-[0_4px_12px_rgba(95,79,209,0.28)]" : "border border-line bg-surface text-ink-2 hover:border-accent",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-1 gap-5 2xl:grid-cols-[minmax(0,1fr)_330px]">
              <div role="tabpanel" className="flex min-w-0 flex-col gap-4">
                {tab === "overview" && (
                  <>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                      <Kpi icon={<Target aria-hidden className="size-6 text-accent" />} tone="bg-accent-soft" label="Models compared" value="5" sub="M0 · M1 · M2 · M3r · M3" />
                      <Kpi icon={<Activity aria-hidden className="size-6 text-sky-ink" />} tone="bg-sky" label="Development episodes" value={lad?.episodes ?? "—"} sub={`${lad?.patients ?? "—"} ${pop === "treated" ? "treated " : ""}patients (T)`} />
                      <Kpi icon={<Gauge aria-hidden className="size-6 text-rose-ink" />} tone="bg-rose" label="Primary metric" value="Sens. @ 1 FA/day" sub="false alerts per patient-day" />
                      <Kpi icon={<Lock aria-hidden className="size-6 text-mint-ink" />} tone="bg-mint" label="Sealed test" value={q.data.confirmatory.split(" ")[0]} sub="70 patients, never opened" />
                    </div>
                    <PlainEvidence ev={q.data} confirmatory={q.data.confirmatory} />
                  </>
                )}
                {tab === "models" && (
                  <>
            <Panel
              title="Model ladder"
              aside={<span className="text-small text-ink-3 tnum">{q.data.ladder[pop]?.patients} patients · {q.data.ladder[pop]?.episodes} episodes</span>}
              bodyClass="p-0 overflow-x-auto"
            >
              <Ladder ev={q.data} pop={pop} />
            </Panel>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <Panel title="Operating curves" aside={<span className="text-[11px] text-ink-4">{q.data.curves ? `curves ${shortHash(q.data.curves.results_sha256, 8)}` : "curves not built"}</span>}>
                {q.data.curves ? <FrocChart ev={q.data} pop={pop} /> : <p className="text-small text-ink-3">Run `hyposense dev evidence` to build the curve artefact.</p>}
              </Panel>
              <Panel title="Paired comparisons · Δ sensitivity @ 1 FA/day">
                <Comparisons ev={q.data} />
              </Panel>
            </div>

                    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                      <Panel title="Operating curves" aside={<span className="text-[11px] text-ink-4">{q.data.curves ? `curves ${shortHash(q.data.curves.results_sha256, 8)}` : "curves not built"}</span>}>
                        {q.data.curves ? <FrocChart ev={q.data} pop={pop} /> : <p className="text-small text-ink-3">Run `hyposense dev evidence` to build the curve artefact.</p>}
                      </Panel>
                      <Panel title="Paired comparisons · Δ sensitivity @ 1 FA/day">
                        <Comparisons ev={q.data} />
                      </Panel>
                    </div>
            {q.data.diagnostics.length > 0 && (
              <Panel
                title="CGM-level reference"
                aside={<StatusTag tone="warn">Post-hoc development reference</StatusTag>}
              >
                <ul className="flex flex-col gap-1">
                  {q.data.diagnostics.map((d) => (
                    <li key={d.label} className="flex items-start justify-between gap-4 text-small">
                      <span className="text-ink-2">{d.label}</span>
                      <span className="text-right text-ink tnum">{d.value}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[11.5px] text-ink-3">
                  This simple reference was added after development analysis and is not a pre-specified
                  confirmatory comparator. M0 is the pre-specified trend baseline; M1/M2/M3r/M3 are the learned
                  models. Values are quoted from the S6 run; the rule was not retuned.
                </p>
              </Panel>
            )}

                  </>
                )}
                {tab === "calibration" && (
                  <Panel
                title="Calibration"
                aside={
                  <select aria-label="Model" className="h-7 rounded-md border border-line-strong px-1.5 text-small" value={calModel} onChange={(e) => setCalModel(e.target.value)}>
                    {MODEL_ORDER.filter((m) => m !== "M0").map((m) => (
                      <option key={m}>{m}</option>
                    ))}
                  </select>
                }
              >
                <ReliabilityChart ev={q.data} pop={pop} model={calModel} />
                <p className="text-[11px] text-ink-4">
                  Reliability bins from the S6 run ({q.data.s6_calibrator}, superseded); deciles of held-out development
                  predictions.
                </p>
                <p className="mt-1 text-small text-ink-3 tnum">
                  Served calibrator <span className="font-medium text-ink">{q.data.calibration_decision}</span>
                  {(() => {
                    const c = (q.data.canonical_calibration?.[pop] as Record<string, Record<string, number>> | undefined)?.[calModel];
                    return c ? ` · ECE ${num(c.ece, 4)} · slope ${num(c.slope, 2)} · log-loss ${num(c.log_loss, 4)} (T, canonical)` : "";
                  })()}
                </p>
                <p className="text-[11px] text-ink-4 tnum">
                  S6 ({q.data.s6_calibrator}): ECE {num(q.data.ladder[pop]?.models[calModel]?.calibration?.ece, 4)} · slope{" "}
                  {num(q.data.ladder[pop]?.models[calModel]?.calibration?.slope, 2)}
                </p>
              </Panel>
                )}
                {tab === "confirmatory" && <ConfirmatoryPanel />}
                {tab === "data" && (
                  <>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
              <Panel title="Prediction task">
                <dl className="grid grid-cols-1 gap-x-8 md:grid-cols-2">
                  <KV k="Target" v={q.data.task.target} />
                  <KV k="Horizon" v={`${q.data.task.horizon_min} min`} />
                  <KV k="Correct warning window" v={`${q.data.task.warning_window_min[0]} to ${q.data.task.warning_window_min[1]} min before onset`} />
                  <KV k="False-alert budget" v={`${q.data.task.fa_budget_per_day} per patient-day`} />
                  <KV k="Primary comparison" v={q.data.task.primary_comparison} />
                  <KV k="Development data" v={q.data.task.population_development} />
                </dl>
                <p className="mt-3 rounded-md bg-sunken px-3 py-2 text-body text-ink-2">{q.data.interpretation}</p>
              </Panel>
              <Panel title="Limitations">
                <ul className="flex list-disc flex-col gap-1.5 pl-4 text-small text-ink-2">
                  {q.data.limitations.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
              </Panel>
            </div>

                    <Panel title="Data quality gates">
                      <Gates ev={q.data} />
                    </Panel>
            <Panel title="Leakage and separation safeguards">
              <ul className="grid grid-cols-1 gap-x-8 gap-y-2 lg:grid-cols-2">
                {q.data.safeguards.map((s) => (
                  <li key={s.label} className="flex items-start justify-between gap-4 border-b border-line py-1.5 last:border-b-0">
                    <span className="text-small text-ink-2">{s.label}</span>
                    <span className="text-right text-small text-ink tnum">
                      {s.value}
                      <span className="block font-mono text-[10.5px] text-ink-4">{s.source}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>

                  </>
                )}
                {tab === "provenance" && (
            <Panel title="Reproducibility and provenance">
              <div className="grid grid-cols-1 gap-x-10 gap-y-4 lg:grid-cols-3">
                <div>
                  <p className="label-caps mb-1">Development run (S6)</p>
                  <dl>
                    <KV k="Run" v={q.data.run_id} mono />
                    <KV k="Results SHA-256" v={shortHash(q.data.results_sha256, 16)} mono />
                    <KV k="Code commit" v={shortHash(q.data.commit, 10)} mono />
                  </dl>
                </div>
                <div>
                  <p className="label-caps mb-1">Live pipeline (S7)</p>
                  {q.data.engineering ? (
                    <dl>
                      <KV k="Offline = live" v={`${q.data.engineering.parity.readings?.toLocaleString()} readings · ${q.data.engineering.parity.probability_mismatch} mismatches`} />
                      <KV k="Replay determinism" v={q.data.engineering.determinism_identical ? "identical decision logs" : "NOT identical"} />
                      <KV k="Malformed-input test" v={`${q.data.engineering.error_injection.later_decisions_changed} later decisions changed`} />
                      <KV k="Latency per reading" v={`p50 ${num(q.data.engineering.latency_ms.p50_ms, 1)} · p99 ${num(q.data.engineering.latency_ms.p99_ms, 1)} ms`} />
                      <KV k="Run" v={shortHash(q.data.engineering.results_sha256, 12)} mono />
                    </dl>
                  ) : (
                    <p className="text-small text-ink-3">No engineering run recorded.</p>
                  )}
                </div>
                <div>
                  <p className="label-caps mb-1">Deployed model</p>
                  <dl>
                    <KV k="Version" v={q.data.model.model_version} mono />
                    <KV k="Status" v={q.data.model.status} />
                    <KV k="Manifest" v={shortHash(q.data.model.manifest_sha256, 12)} mono />
                    <KV k="Feature spec" v={shortHash(q.data.model.compatibility.feature_spec_sha256, 12)} mono />
                    <KV k="Config" v={shortHash(q.data.model.compatibility.config_sha256, 12)} mono />
                    <KV k="ALERT / WATCH thresholds" v={`${pct(q.data.model.tau_alert)} / ${pct(q.data.model.tau_watch)}`} />
                  </dl>
                </div>
              </div>
            </Panel>
                )}
              </div>
              <div className="grid grid-cols-1 content-start gap-4 xl:grid-cols-2 2xl:grid-cols-1">
                <Panel title="Dataset overview">
                  <ul className="flex flex-col gap-3">
                    {DATASET.map(([a, b, src]) => (
                      <li key={a} className="flex gap-3">
                        <span className="mt-1 size-2.5 shrink-0 rounded-full bg-accent" aria-hidden />
                        <span>
                          <span className="block text-small font-semibold text-ink">{a}</span>
                          <span className="block text-[12px] text-ink-3">
                            {b} · <span className="font-mono text-[10.5px]">{src}</span>
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </Panel>
                <section aria-label="Key takeaways" className="card bg-gradient-to-br from-[#fff8ec] to-white p-5">
                  <p className="flex items-center gap-2 text-section font-bold text-ink">
                    <Lightbulb aria-hidden className="size-5 text-peach-ink" /> Key takeaways (development)
                  </p>
                  <ul className="mt-2 flex flex-col gap-2 text-small text-ink-2">
                    <li>Learned models warn far more episodes than the simple trend rule at the same false-alert budget.</li>
                    <li>
                      M3 − M2: {d?.point != null ? `${d.point > 0 ? "+" : ""}${(d.point * 100).toFixed(1)}` : "—"} points
                      {d?.ci95 ? ` (95% CI ${(d.ci95[0]! * 100).toFixed(1)} to ${(d.ci95[1]! * 100).toFixed(1)})` : ""} — the interval includes zero, so
                      no reliable benefit of medication exposure is shown yet.
                    </li>
                    <li>A post-hoc CGM-level rule matches the learned models on development data (see Model comparison).</li>
                    <li>The decisive test runs once on the sealed patients after the protocol freeze; its result will be shown whatever it is.</li>
                  </ul>
                </section>
              </div>
            </div>
            <p className="text-[12px] text-ink-4">{q.data.caveat}</p>
          </>
        )}
      </div>
    </div>
  );
}
