"use client";
import clsx from "clsx";
import { Lock } from "lucide-react";
import { num, pct, shortHash } from "@/lib/format";
import { useConfirmatory } from "@/lib/queries";
import { ErrorBox, KV, Panel, Skeleton, StatusTag } from "@/components/ui/primitives";
import { IntervalBar, MODEL_COLOR, MODEL_DESC, MODEL_ORDER } from "@/components/evidence/EvidenceCharts";

/** Shape of GET /api/confirmatory (backend `evaluation.confirm_view`). Every number is copied
 *  from the single official S9 results document; nothing is computed here. */
type Interval = { point: number | null; ci95: [number, number] | null };
type Row = {
  key: string;
  group: string;
  label: string;
  available: boolean;
  patients?: number;
  episodes?: number;
  M2_sens1?: number | null;
  M3_sens1?: number | null;
  delta?: number | null;
  delta_ci95?: [number, number] | null;
};
export type ConfirmatoryDoc = {
  status: string;
  note?: string;
  run_id?: string;
  results_sha256?: string;
  commit?: string;
  freeze?: { freeze_id: string; record_sha256: string; source_commit: string } | null;
  population?: Record<string, number>;
  primary?: {
    M2_sens_at_1fa: number;
    M3_sens_at_1fa: number;
    delta: number;
    delta_ci95: [number, number];
    undefined_resamples: number;
    g5_pass: boolean;
    h1_supported: boolean;
  };
  ladder?: Record<string, { sens1: number | null; sens1_ci95: [number, number] | null; logloss: number | null }>;
  contrasts?: Record<string, Interval>;
  s2_matched_sensitivity_fa_delta?: Interval;
  selection?: { selected: string; steps: string[] };
  interpretation?: string[];
  deployed_operating_point?: Record<
    string,
    { sensitivity: number | null; fa_per_day: number | null; alert_precision: number | null; lead_median_min: number | null }
  >;
  analyses?: Row[];
};

const signed = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${(Math.abs(v) * 100).toFixed(d)} pp`;
const ciText = (ci: [number, number] | null | undefined) =>
  ci ? `${signed(ci[0])} to ${signed(ci[1])}` : "";

function Pending({ note }: { note?: string }) {
  return (
    <div className="flex items-start gap-3 text-small text-ink-2">
      <Lock aria-hidden className="mt-0.5 size-4 shrink-0 text-ink-3" />
      <div>
        <p className="font-semibold text-ink">Confirmatory result: PENDING</p>
        <p className="mt-0.5">{note}</p>
        <p className="mt-1 text-ink-3">
          Primary hypothesis H1: the lower 95% bound of Δ sensitivity @ 1 FA/day (M3 − M2) on treated patients of the
          sealed partition is above 0. The numbers below this panel are development evidence on the tuning partition.
        </p>
      </div>
    </div>
  );
}

function Analyses({ rows }: { rows: Row[] }) {
  return (
    <table className="w-full text-small">
      <caption className="sr-only">Pre-specified secondary, sensitivity and robustness analyses</caption>
      <thead>
        <tr className="border-b border-line bg-[#fafbfc] text-left">
          {["Analysis", "Patients", "Episodes", "M2", "M3", "Δ M3 − M2 (95% CI)"].map((h, i) => (
            <th key={h} scope="col" className={clsx("label-caps px-3 py-2", i >= 1 && "text-right")}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} className={clsx("border-b border-line last:border-b-0", r.group === "Primary" && "bg-accent-soft/40")}>
            <th scope="row" className="px-3 py-1.5 text-left font-normal text-ink-2">
              <span className="mr-2 text-[10.5px] uppercase tracking-wide text-ink-4">{r.group}</span>
              {r.label}
            </th>
            {r.available ? (
              <>
                <td className="px-3 py-1.5 text-right tnum">{r.patients ?? "—"}</td>
                <td className="px-3 py-1.5 text-right tnum">{r.episodes ?? "—"}</td>
                <td className="px-3 py-1.5 text-right tnum">{pct(r.M2_sens1)}</td>
                <td className="px-3 py-1.5 text-right tnum">{pct(r.M3_sens1)}</td>
                <td className="px-3 py-1.5 text-right tnum">
                  {signed(r.delta)} <span className="text-ink-4">{ciText(r.delta_ci95)}</span>
                </td>
              </>
            ) : (
              <td colSpan={5} className="px-3 py-1.5 text-right text-ink-4">
                not available
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Result({ c }: { c: ConfirmatoryDoc }) {
  const p = c.primary!;
  const official = c.status === "CONFIRMATORY";
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-md border border-line p-3">
          <p className="label-caps">Primary endpoint · treated patients</p>
          <p className="mt-1 text-[22px] font-semibold text-ink tnum">{signed(p.delta)}</p>
          <p className="text-small text-ink-3 tnum">
            95% CI {ciText(p.delta_ci95)} · M2 {pct(p.M2_sens_at_1fa)} → M3 {pct(p.M3_sens_at_1fa)}
          </p>
          <p className="mt-2">
            <StatusTag tone={p.h1_supported ? "ok" : "neutral"}>{p.h1_supported ? "H1 supported" : "H1 not supported"}</StatusTag>
            <span className="ml-2 text-[11px] text-ink-4 tnum">
              G5 {p.g5_pass ? "pass" : "FAIL"} · {p.undefined_resamples} undefined resamples
            </span>
          </p>
        </div>
        <div className="rounded-md border border-line p-3">
          <p className="label-caps">Model selection (pre-specified rule)</p>
          <p className="mt-1 text-[22px] font-semibold text-ink">{c.selection?.selected}</p>
          <ul className="text-small text-ink-3">
            {c.selection?.steps.map((s) => <li key={s}>{s}</li>)}
          </ul>
        </div>
        <div className="rounded-md border border-line p-3">
          <p className="label-caps">Interpretation (Table 20.4, mechanical)</p>
          <ul className="mt-1 list-disc pl-4 text-small text-ink-2">
            {c.interpretation?.length ? c.interpretation.map((s) => <li key={s}>{s}</li>) : <li>No row applies</li>}
          </ul>
        </div>
      </div>
      <table className="w-full text-small">
        <caption className="sr-only">Model ladder on the primary population</caption>
        <thead>
          <tr className="border-b border-line bg-[#fafbfc] text-left">
            {["Model", "Inputs", "Sensitivity @ 1 FA/day (95% CI)", "", "Log-loss", "Deployed: sens · FA/day · precision"].map((h, i) => (
              <th key={i} scope="col" className={clsx("label-caps px-3 py-2", i >= 4 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {MODEL_ORDER.filter((m) => c.ladder?.[m]).map((m) => {
            const x = c.ladder![m]!;
            const d = c.deployed_operating_point?.[m];
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
                  <span className="font-semibold text-ink">{pct(x.sens1)}</span>
                  <span className="ml-1.5 text-ink-3">{x.sens1_ci95 ? `${pct(x.sens1_ci95[0])}–${pct(x.sens1_ci95[1])}` : ""}</span>
                </td>
                <td className="px-3 py-2">
                  <IntervalBar point={x.sens1} ci={x.sens1_ci95} lo={0.4} hi={1} color={MODEL_COLOR[m]} />
                </td>
                <td className="px-3 py-2 text-right tnum">{num(x.logloss, 4)}</td>
                <td className="px-3 py-2 text-right tnum">
                  {d ? `${pct(d.sensitivity)} · ${num(d.fa_per_day, 2)} · ${pct(d.alert_precision)}` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {c.analyses && <Analyses rows={c.analyses} />}
      <dl className="grid grid-cols-1 gap-x-10 lg:grid-cols-3">
        <KV k="Run" v={c.run_id} mono />
        <KV k="Results SHA-256" v={shortHash(c.results_sha256, 16)} mono />
        <KV k="Freeze record" v={c.freeze ? shortHash(c.freeze.record_sha256, 16) : "—"} mono />
      </dl>
      {!official && <p className="text-[11.5px] font-semibold text-watch-ink">{c.status}: not evidence.</p>}
    </div>
  );
}

export function ConfirmatoryPanel() {
  const q = useConfirmatory();
  const status = q.data?.status;
  return (
    <Panel
      title="Confirmatory evaluation (sealed partition)"
      aside={
        status && (
          <StatusTag tone={status === "CONFIRMATORY" ? "ok" : status === "PENDING" ? "neutral" : "warn"}>{status}</StatusTag>
        )
      }
    >
      {q.isError && <ErrorBox title="Confirmatory result unavailable" detail={(q.error as Error).message} onRetry={() => q.refetch()} />}
      {!q.data && !q.isError && <Skeleton className="h-24 w-full" />}
      {q.data && (q.data.primary ? <Result c={q.data} /> : q.data.status === "PENDING" ? <Pending note={q.data.note} /> : (
        <p role="alert" className="text-small font-semibold text-alert-ink">
          {q.data.status}: {q.data.note}
        </p>
      ))}
    </Panel>
  );
}
