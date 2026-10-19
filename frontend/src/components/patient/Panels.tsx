"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDown, ArrowUp, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { api, ApiError, type AckRequest, type PatientView } from "@/lib/api";
import { age, bedLabel, clock, mgdl, rate } from "@/lib/format";
import { stateMeaning, stateStyle, TREND } from "@/lib/states";
import { Button, Details, InfoTag, KV, Panel, QualityBadge, StatePill } from "@/components/ui/primitives";

export function PatientHeader({ v, offsetS }: { v: PatientView; offsetS: number }) {
  const s = stateStyle(v.current.state);
  const m = stateMeaning(v.current.state);
  const tr = v.trend.category ? TREND[v.trend.category] : undefined;
  const lastTs = v.timeline.length ? v.timeline[v.timeline.length - 1]!.ts : null;
  const noForecastWhy = v.current.texts.slice(1).join(" ") || v.current.texts[0];
  return (
    <section aria-label="What is happening now" className="relative overflow-hidden rounded-lg border border-line bg-surface">
      <span aria-hidden className={clsx("absolute inset-y-0 left-0 w-1", s.bar === "bg-transparent" ? "bg-line" : s.bar)} />
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(280px,1.3fr)_minmax(200px,0.8fr)_minmax(220px,0.9fr)] lg:divide-x lg:divide-line">
        <div className="flex flex-col gap-2 px-5 py-4">
          <p className="label-caps">What is happening now?</p>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-display font-semibold tracking-tight text-ink">{bedLabel(v.recording_key, v.label)}</h1>
            <StatePill state={v.current.state} size="lg" explain />
          </div>
          <p className="text-body text-ink-2">{m.text}</p>
          <div className="flex flex-wrap gap-1.5">
            {v.input_rejected && <QualityBadge code="INPUT_REJECTED" />}
            {v.halted && <QualityBadge code="RUNNER_HALTED" />}
            {v.data_quality.includes("SENSOR_FAULT_SUSPECTED") && <QualityBadge code="SENSOR_FAULT_SUSPECTED" />}
            {v.current.tags.map((t) => (
              <InfoTag key={t} tag={t} />
            ))}
          </div>
        </div>
        <div className="flex flex-col justify-center gap-0.5 border-t border-line px-5 py-4 lg:border-t-0">
          <p className="label-caps flex items-center gap-1.5">
            <span aria-hidden className="size-2 rounded-full bg-ink" /> Observed now · CGM
          </p>
          <p className={clsx("text-metric font-semibold tnum", v.cgm_low ? "text-low-ink" : "text-ink")}>
            {mgdl(v.cgm_mgdl)}
            <span className="ml-1 text-small font-normal text-ink-3">mg/dL</span>
          </p>
          <p className="text-small text-ink-2 tnum">
            {tr ? `${tr.glyph} ${tr.text} (${rate(v.trend.rate_mgdl_per_min)} mg/dL per min)` : "trend unavailable"}
          </p>
          <p className={clsx("text-small tnum", v.stale ? "font-semibold text-alert-ink" : "text-ink-3")}>
            {v.stale ? "Not current — " : ""}last reading {age(v.data_age_s)}
            {lastTs !== null ? ` · ${clock(lastTs, offsetS)}` : ""}
          </p>
        </div>
        <div className="m-3 flex flex-col justify-center gap-0.5 rounded-md border border-dashed border-line-strong bg-[#fafbfc] px-4 py-3">
          <p className="label-caps flex items-center gap-1.5">
            <span aria-hidden className="size-2 rounded-full border border-ink-3" /> Predicted · next 60 min
          </p>
          {v.current.p_text ? (
            <>
              <p className={clsx("text-metric font-semibold tnum", s.ink)}>{v.current.p_text}</p>
              <p className="text-small text-ink-2">estimated risk that a new CGM-detected low begins</p>
              <p className="text-[11px] font-medium text-watch-ink">{v.model_status} model · not clinically validated</p>
            </>
          ) : (
            <>
              <p className="text-title font-semibold text-ink-3">No forecast</p>
              <p className="text-small text-ink-2">{noForecastWhy}</p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

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

export function WhyPanel({ v, tauAlert, tauWatch }: { v: PatientView; tauAlert?: number | null; tauWatch?: number | null }) {
  const max = Math.max(1e-9, ...v.factor_groups.map((g) => Math.abs(g.contribution)));
  const [headline, ...more] = v.current.texts;
  return (
    <Panel title="Why is HypoSense showing this?" id="why">
      <p className="text-body font-medium text-ink">{headline}</p>
      {more.length > 0 && (
        <ul className="mt-1 flex flex-col gap-0.5">
          {more.map((t) => (
            <li key={t} className="text-small text-ink-2">
              {t}
            </li>
          ))}
        </ul>
      )}
      <p className="label-caps mb-2 mt-4">Information associated with this estimate</p>
      {v.factor_groups.length === 0 ? (
        <p className="text-small text-ink-3">
          {v.current.p === null ? "There is no estimate in this state, so nothing is attributed." : "Attribution unavailable for this estimate."}
        </p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Factor groups">
          {v.factor_groups.map((g) => (
            <li key={g.group} className="grid grid-cols-[18px_1fr_auto] items-center gap-2">
              {g.direction === "raises_risk" ? (
                <ArrowUp aria-label="pushes the estimate up" className="size-3.5 text-alert" />
              ) : (
                <ArrowDown aria-label="pushes the estimate down" className="size-3.5 text-ink-3" />
              )}
              <div>
                <p className="text-body text-ink">{GROUP_PLAIN[g.group] ?? g.label}</p>
                <div className="mt-1 h-1.5 rounded-full bg-sunken">
                  <div
                    className={clsx("h-1.5 rounded-full", g.direction === "raises_risk" ? "bg-alert/70" : "bg-ink-4/60")}
                    style={{ width: `${(100 * Math.abs(g.contribution)) / max}%` }}
                  />
                </div>
              </div>
              <span className="text-[11px] text-ink-3">{g.direction === "raises_risk" ? "pushes up" : "pushes down"}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-[11.5px] text-ink-3">
        Statistical associations with this estimate — not causes of low glucose, and not a reason to change treatment.
      </p>
      <div className="mt-3">
        <Details summary="Technical detail">
          <dl>
            <KV k="Policy state" v={v.current.state} mono />
            <KV k="Calibrated probability" v={v.current.p === null ? "—" : `${(v.current.p * 100).toFixed(2)} %`} />
            <KV k="Alert threshold (τA)" v={tauAlert == null ? "—" : `${(tauAlert * 100).toFixed(2)} %`} />
            <KV k="Watch threshold (τW)" v={tauWatch == null ? "—" : `${(tauWatch * 100).toFixed(2)} %`} />
            <KV k="Reason codes" v={v.current.reasons.join(", ") || "—"} mono />
            <KV k="Tags" v={v.current.tags.join(", ") || "—"} mono />
            <KV k="Decision" v={v.current.decision_id ?? "—"} mono />
          </dl>
          <p className="mt-2 text-[11px] text-ink-3">
            Attribution: grouped TreeSHAP on the model’s raw score before calibration, summed per feature group (top 3 shown).
            Thresholds are frozen in the model artefact; the policy (not the model) turns the probability into a state.
          </p>
        </Details>
      </div>
    </Panel>
  );
}

const MED_TEXT: Record<string, string> = {
  KNOWN: "doses recorded",
  PARTIAL: "partially known",
  TIMING_UNKNOWN: "prescribed, dose times not recorded",
  DOSE_UNKNOWN: "dose unknown",
  FORMULATION_UNKNOWN: "formulation unknown",
  NO_LOGGED_MEDICATION: "none recorded",
};
const DQ_TEXT: Record<string, string> = {
  AFTER_GAP: "First reading after a data gap",
  INSUFFICIENT_HISTORY: "Too few recent readings",
  WARM_UP: "Sensor warm-up period",
  SENSOR_FLOOR: "Reading at the sensor floor",
  RAPID_CHANGE: "Rapid glucose change",
  SENSOR_FAULT_SUSPECTED: "Sensor fault suspected",
};

export function QualityPanel({ v }: { v: PatientView }) {
  return (
    <Panel title="Can the data be trusted right now?">
      <dl>
        <KV k="Recent CGM data" v={v.data_quality.length ? v.data_quality.map((q) => DQ_TEXT[q] ?? q).join("; ") : "enough for a forecast"} />
        {Object.entries(v.medication_quality).map(([c, q]) => (
          <KV key={c} k={`${c[0]!.toUpperCase()}${c.slice(1)}`} v={MED_TEXT[q] ?? q} />
        ))}
        <KV k="Inputs that could not be used" v={v.rejected_events} />
        <KV k="Processing" v={v.halted ? "halted (reset required)" : "running"} />
      </dl>
    </Panel>
  );
}

const REASONS: Array<[AckRequest["reason"], string]> = [
  ["checked_glucose", "Capillary glucose checked"],
  ["known", "Known / already managed"],
  ["sensor_issue", "Sensor issue suspected"],
  ["not_relevant", "Not clinically relevant"],
];

export function AckPanel({ v, offsetS }: { v: PatientView; offsetS: number }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [reason, setReason] = useState<AckRequest["reason"] | null>(null);
  const [role, setRole] = useState<AckRequest["user_role"]>("nurse");
  const ack = useMutation({
    mutationFn: (req: AckRequest) => api.acknowledge(req),
    onSuccess: () => {
      setOpen(null);
      setReason(null);
      qc.invalidateQueries({ queryKey: ["patient"] });
      qc.invalidateQueries({ queryKey: ["ward"] });
    },
  });
  const pending = v.notifications.filter((n) => !n.acknowledged);
  const done = v.notifications.filter((n) => n.acknowledged);
  return (
    <Panel title="Alerts to acknowledge" aside={<span className="text-small text-ink-3 tnum">{pending.length} awaiting</span>}>
      {v.notifications.length === 0 && <p className="text-small text-ink-3">No notifications yet.</p>}
      <ul className="flex flex-col gap-1.5">
        {[...pending].reverse().map((n) => (
          <li key={n.decision_id} className="flex items-center justify-between gap-2 rounded-md border border-alert-line bg-alert-tint px-3 py-2">
            <span className="text-body text-alert-ink">
              ALERT notification · <span className="tnum">{clock(n.ts, offsetS)}</span>
            </span>
            <Dialog.Root
              open={open === n.decision_id}
              onOpenChange={(o) => {
                setOpen(o ? n.decision_id : null);
                setReason(null);
                ack.reset();
              }}
            >
              <Dialog.Trigger asChild>
                <Button size="sm">Acknowledge…</Button>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/25" />
                <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-line bg-surface p-5 shadow-[0_12px_40px_rgba(16,24,40,0.18)]">
                  <Dialog.Title className="text-title font-semibold text-ink">Acknowledge notification</Dialog.Title>
                  <Dialog.Description className="mt-1 text-small text-ink-3">
                    {bedLabel(v.recording_key)} · ALERT at {clock(n.ts, offsetS)}. Recorded in the audit log; it cannot be undone.
                  </Dialog.Description>
                  <fieldset className="mt-4 flex flex-col gap-1.5">
                    <legend className="label-caps mb-1">Reason</legend>
                    {REASONS.map(([code, text]) => (
                      <label key={code} className="flex cursor-pointer items-center gap-2 rounded-md border border-line px-3 py-2 text-body hover:bg-sunken has-[:checked]:border-accent has-[:checked]:bg-accent-soft">
                        <input type="radio" name="reason" className="accent-[var(--color-accent)]" checked={reason === code} onChange={() => setReason(code)} />
                        {text}
                      </label>
                    ))}
                  </fieldset>
                  <label className="mt-3 flex items-center justify-between text-body text-ink-2">
                    Role
                    <select className="h-8 rounded-md border border-line-strong bg-surface px-2" value={role} onChange={(e) => setRole(e.target.value as AckRequest["user_role"])}>
                      <option value="nurse">Nurse</option>
                      <option value="physician">Physician</option>
                      <option value="researcher">Researcher</option>
                    </select>
                  </label>
                  {ack.isError && (
                    <p role="alert" className="mt-2 text-small text-low-ink">
                      {ack.error instanceof ApiError ? ack.error.message : "Not recorded."}
                    </p>
                  )}
                  <div className="mt-5 flex justify-end gap-2">
                    <Dialog.Close asChild>
                      <Button>Cancel</Button>
                    </Dialog.Close>
                    <Button
                      variant="primary"
                      disabled={!reason || ack.isPending}
                      onClick={() => reason && ack.mutate({ decision_id: n.decision_id, reason, user_role: role })}
                    >
                      Record acknowledgement
                    </Button>
                  </div>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </li>
        ))}
        {[...done].reverse().map((n) => (
          <li key={n.decision_id} className="flex items-center gap-2 px-1 py-1 text-small text-ink-3">
            <CheckCircle2 aria-hidden className="size-3.5 text-ink-4" />
            <span className="tnum">{clock(n.ts, offsetS)}</span> acknowledged · {REASONS.find(([c]) => c === n.reason)?.[1] ?? n.reason}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

const OUTCOME: Record<string, { text: string; cls: string }> = {
  LOW_FOLLOWED: { text: "A CGM low followed", cls: "text-low-ink font-medium" },
  NO_LOW: { text: "No CGM low followed", cls: "text-ink-2" },
  PENDING: { text: "Waiting — the 60 min are not over yet", cls: "text-ink-3" },
  OUTCOME_UNKNOWN: { text: "Unknown — the recording ended", cls: "text-ink-3" },
};

export function LedgerPanel({ v, offsetS }: { v: PatientView; offsetS: number }) {
  const [all, setAll] = useState(false);
  const rows = v.ledger_entries.filter((e) => all || e.notified || e.state === "ALERT" || e.state === "WATCH" || e.outcome === "LOW_FOLLOWED" || e.outcome === "PENDING");
  return (
    <Panel
      id="history"
      title="What happened after each forecast?"
      aside={
        <div className="flex items-center gap-4 text-small text-ink-3 tnum">
          <span>{v.ledger.resolved_low} followed by a low · {v.ledger.resolved_no_low} not followed · {v.ledger.pending} still open</span>
          <label className="flex items-center gap-1.5">
            <input type="checkbox" className="accent-[var(--color-accent)]" checked={all} onChange={(e) => setAll(e.target.checked)} />
            all forecasts
          </label>
        </div>
      }
      bodyClass="p-0"
    >
      <p className="border-b border-line px-4 py-2 text-[11.5px] text-ink-3">
        Each forecast is later checked against what the CGM actually showed in the following 60 minutes. Earlier forecasts
        are never changed afterwards. {all ? "Showing all recent forecasts." : "Showing WATCH and ALERT forecasts, notifications and any forecast followed by a low."}
      </p>
      {rows.length === 0 ? (
        <p className="px-4 py-6 text-center text-small text-ink-3">No entries yet.</p>
      ) : (
        <table className="w-full text-small">
          <thead>
            <tr className="border-b border-line bg-[#fafbfc] text-left">
              {["Forecast at", "State", "Estimated risk", "Notified", "What the CGM showed in the next 60 min", "Known at"].map((h) => (
                <th key={h} scope="col" className="label-caps px-4 py-2 font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 25).map((e) => (
              <tr key={e.forecast_ts} className="border-b border-line last:border-b-0">
                <td className="px-4 py-1.5 tnum">{clock(e.forecast_ts, offsetS)}</td>
                <td className="px-4 py-1.5">{e.state ? <StatePill state={e.state} size="sm" /> : "—"}</td>
                <td className="px-4 py-1.5 tnum">{e.p_text}</td>
                <td className="px-4 py-1.5">{e.notified ? "yes" : "—"}</td>
                <td className={clsx("px-4 py-1.5", OUTCOME[e.outcome]?.cls)}>{OUTCOME[e.outcome]?.text ?? e.outcome}</td>
                <td className="px-4 py-1.5 tnum text-ink-3">{e.resolved_ts ? clock(e.resolved_ts, offsetS) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
