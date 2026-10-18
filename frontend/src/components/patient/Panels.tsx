"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDown, ArrowUp, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { api, ApiError, type AckRequest, type PatientView } from "@/lib/api";
import { age, bedLabel, clock, mgdl, rate } from "@/lib/format";
import { stateStyle, TREND } from "@/lib/states";
import { Button, InfoTag, KV, Panel, QualityBadge, StatePill } from "@/components/ui/primitives";

export function PatientHeader({ v, offsetS }: { v: PatientView; offsetS: number }) {
  const s = stateStyle(v.current.state);
  const tr = v.trend.category ? TREND[v.trend.category] : undefined;
  return (
    <section aria-label="Current state" className="relative overflow-hidden rounded-lg border border-line bg-surface">
      <span aria-hidden className={clsx("absolute inset-y-0 left-0 w-1", s.bar === "bg-transparent" ? "bg-line" : s.bar)} />
      <div className="grid grid-cols-[minmax(260px,1.4fr)_repeat(3,minmax(120px,0.6fr))] items-stretch divide-x divide-line">
        <div className="flex flex-col gap-2 px-5 py-4">
          <div className="flex items-center gap-3">
            <h1 className="text-display font-semibold tracking-tight text-ink">{bedLabel(v.recording_key)}</h1>
            <StatePill state={v.current.state} size="lg" />
          </div>
          <p className="text-body text-ink-2">{v.summary}</p>
          <div className="flex flex-wrap gap-1.5">
            {v.input_rejected && <QualityBadge code="INPUT_REJECTED" />}
            {v.halted && <QualityBadge code="RUNNER_HALTED" />}
            {v.data_quality.includes("SENSOR_FAULT_SUSPECTED") && <QualityBadge code="SENSOR_FAULT_SUSPECTED" />}
            {v.current.tags.map((t) => (
              <InfoTag key={t} tag={t} />
            ))}
          </div>
        </div>
        <div className="flex flex-col justify-center px-5 py-4">
          <p className="label-caps">CGM (observed)</p>
          <p className={clsx("text-metric font-semibold tnum", v.cgm_mgdl !== null && v.cgm_mgdl < 70 ? "text-low-ink" : "text-ink")}>
            {mgdl(v.cgm_mgdl)}
            <span className="ml-1 text-small font-normal text-ink-3">mg/dL</span>
          </p>
          <p className="text-small text-ink-3 tnum">
            {tr ? `${tr.glyph} ${tr.text} · ${rate(v.trend.rate_mgdl_per_min)} /min` : "trend unavailable"}
          </p>
        </div>
        <div className="flex flex-col justify-center px-5 py-4">
          <p className="label-caps">Risk · next 60 min</p>
          <p className={clsx("text-metric font-semibold tnum", v.current.p_text ? s.ink : "text-ink-4")}>
            {v.current.p_text ?? "—"}
          </p>
          <p className="text-small text-ink-3">{v.current.p_text ? `${v.model_status} model` : "no forecast in this state"}</p>
        </div>
        <div className="flex flex-col justify-center px-5 py-4">
          <p className="label-caps">Last reading</p>
          <p className={clsx("text-title font-semibold tnum", v.data_age_s !== null && v.data_age_s > 1200 ? "text-alert-ink" : "text-ink")}>
            {age(v.data_age_s)}
          </p>
          <p className="text-small text-ink-3 tnum">{v.timeline.length ? clock(v.timeline[v.timeline.length - 1]!.ts, offsetS) : "—"} record clock</p>
        </div>
      </div>
    </section>
  );
}

export function WhyPanel({ v }: { v: PatientView }) {
  const max = Math.max(1e-9, ...v.factor_groups.map((g) => Math.abs(g.contribution)));
  return (
    <Panel title="Why this state">
      <ul className="mb-3 flex flex-col gap-1">
        {v.current.texts.map((t) => (
          <li key={t} className="text-body text-ink-2">
            {t}
          </li>
        ))}
      </ul>
      <p className="label-caps mb-2">Factors associated with this forecast</p>
      {v.factor_groups.length === 0 ? (
        <p className="text-small text-ink-3">
          {v.current.p === null
            ? "No forecast in the current state, so no attribution is shown."
            : "Attribution unavailable for this forecast."}
        </p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Factor groups">
          {v.factor_groups.map((g) => (
            <li key={g.group} className="grid grid-cols-[18px_1fr_auto] items-center gap-2">
              {g.direction === "raises_risk" ? (
                <ArrowUp aria-label="raises estimated risk" className="size-3.5 text-alert" />
              ) : (
                <ArrowDown aria-label="lowers estimated risk" className="size-3.5 text-ink-3" />
              )}
              <div>
                <p className="text-body text-ink">{g.label}</p>
                <div className="mt-1 h-1.5 rounded-full bg-sunken">
                  <div
                    className={clsx("h-1.5 rounded-full", g.direction === "raises_risk" ? "bg-alert/70" : "bg-ink-4/60")}
                    style={{ width: `${(100 * Math.abs(g.contribution)) / max}%` }}
                  />
                </div>
              </div>
              <span className="text-[11px] text-ink-4">{g.direction === "raises_risk" ? "raises" : "lowers"}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[11px] leading-4 text-ink-4">
        Grouped TreeSHAP on the model’s raw score (before calibration). These are statistical associations with this
        forecast, not causes of low glucose.
      </p>
    </Panel>
  );
}

const MED_TEXT: Record<string, string> = {
  KNOWN: "logged",
  PARTIAL: "partially known",
  TIMING_UNKNOWN: "timing unknown",
  DOSE_UNKNOWN: "dose unknown",
  FORMULATION_UNKNOWN: "formulation unknown",
  NO_LOGGED_MEDICATION: "none logged",
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
    <Panel title="Data quality">
      <dl>
        <KV k="CGM sufficiency" v={v.data_quality.length ? v.data_quality.map((q) => DQ_TEXT[q] ?? q).join("; ") : "sufficient"} />
        {Object.entries(v.medication_quality).map(([c, q]) => (
          <KV key={c} k={`${c[0]!.toUpperCase()}${c.slice(1)} record`} v={MED_TEXT[q] ?? q} />
        ))}
        <KV k="Rejected input events" v={v.rejected_events} />
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
    <Panel title="Notifications" aside={<span className="text-small text-ink-3 tnum">{pending.length} awaiting</span>}>
      {v.notifications.length === 0 && <p className="text-small text-ink-3">No notifications in this replay yet.</p>}
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
  LOW_FOLLOWED: { text: "CGM low followed", cls: "text-low-ink font-medium" },
  NO_LOW: { text: "No CGM low", cls: "text-ink-2" },
  PENDING: { text: "Pending (window open)", cls: "text-ink-3" },
  OUTCOME_UNKNOWN: { text: "Unknown (record ended)", cls: "text-ink-3" },
};

export function LedgerPanel({ v, offsetS }: { v: PatientView; offsetS: number }) {
  const [all, setAll] = useState(false);
  const rows = v.ledger_entries.filter((e) => all || e.notified || e.state === "ALERT" || e.state === "WATCH" || e.outcome === "LOW_FOLLOWED" || e.outcome === "PENDING");
  return (
    <Panel
      title="Forecast → outcome ledger"
      aside={
        <div className="flex items-center gap-4 text-small text-ink-3 tnum">
          <span>{v.ledger.resolved_low} followed by a low · {v.ledger.resolved_no_low} not · {v.ledger.pending} pending</span>
          <label className="flex items-center gap-1.5">
            <input type="checkbox" className="accent-[var(--color-accent)]" checked={all} onChange={(e) => setAll(e.target.checked)} />
            all forecasts
          </label>
        </div>
      }
      bodyClass="p-0"
    >
      <p className="border-b border-line px-4 py-2 text-[11.5px] text-ink-3">
        Each forecast is reconciled by the twin with what the CGM showed in the following 60 minutes (causal; no
        hindsight relabelling). {all ? "Showing all recent forecasts." : "Showing WATCH/ALERT forecasts, notifications and forecasts followed by a low."}
      </p>
      {rows.length === 0 ? (
        <p className="px-4 py-6 text-center text-small text-ink-3">No entries yet.</p>
      ) : (
        <table className="w-full text-small">
          <thead>
            <tr className="border-b border-line bg-[#fafbfc] text-left">
              {["Forecast time", "State", "Risk", "Notified", "Outcome (next 60 min)", "Known at"].map((h) => (
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
