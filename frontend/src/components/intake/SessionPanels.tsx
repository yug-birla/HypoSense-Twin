"use client";
// New-data session controls on Patient review. Observations are validated and processed by the
// server (canonical adapter → twin); the browser only collects the entry.
import { useQueryClient } from "@tanstack/react-query";
import { DatabaseZap, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError, type ObservationResult, type PatientView } from "@/lib/api";
import { STATE } from "@/lib/states";
import { Button, Panel } from "@/components/ui/primitives";

export function SessionBanner({ v }: { v: PatientView }) {
  return (
    <div role="note" className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-lg border border-watch-line bg-watch-tint px-5 py-2.5 text-watch-ink">
      <span className="inline-flex items-center gap-2 text-body font-bold uppercase tracking-wider">
        <DatabaseZap aria-hidden className="size-4" /> New data session
      </span>
      <span className="text-small">DEVELOPMENT model · not clinically validated · not research data</span>
      <span className="text-small">Times are the patient’s local clock · {v.label ? `label “${v.label}”` : "no label"}</span>
    </div>
  );
}

type Kind = "cgm" | "cbg" | "meal" | "medication";
const KINDS: { k: Kind; label: string }[] = [
  { k: "cgm", label: "CGM reading" },
  { k: "cbg", label: "Capillary glucose" },
  { k: "meal", label: "Meal" },
  { k: "medication", label: "Medication given" },
];

function nowLocal(ts: number, offsetS: number): string {
  const d = new Date((ts + offsetS + 300) * 1000); // default: 5 min after the latest event
  return d.toISOString().slice(0, 16).replace("T", " ");
}

export function ObservationPanel({ v, offsetS }: { v: PatientView; offsetS: number }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState<Kind>("cgm");
  const [time, setTime] = useState(() => nowLocal(v.now_ts, offsetS));
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("mg/dL");
  const [text, setText] = useState("");
  const [column, setColumn] = useState("insulin_sc");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const submit = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const glucose = kind === "cgm" || kind === "cbg";
      const r: ObservationResult = await api.observe(v.recording_key, {
        kind,
        local_time: time.trim(),
        value: glucose ? Number(value) : null,
        unit: glucose ? unit : null,
        text: glucose ? null : text,
        column: kind === "medication" ? column : null,
      });
      const states = r.decisions.map((s) => STATE[s as keyof typeof STATE]?.label ?? s).join(", ");
      setMsg({ ok: true, text: `Added ${r.kind} at ${r.local_time}${states ? ` → ${states}` : ""}.` });
      setValue("");
      setText("");
      await qc.invalidateQueries({ queryKey: ["patient"] });
      await qc.invalidateQueries({ queryKey: ["ward"] });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : "Unexpected error" });
    } finally {
      setBusy(false);
    }
  };
  const glucose = kind === "cgm" || kind === "cbg";
  const ready = time.trim() && (glucose ? value.trim() !== "" : kind === "meal" || text.trim());
  return (
    <Panel title="Add observation">
      <div role="radiogroup" aria-label="Observation type" className="mb-3 flex flex-wrap gap-1">
        {KINDS.map(({ k, label }) => (
          <button
            key={k}
            role="radio"
            aria-checked={kind === k}
            type="button"
            onClick={() => setKind(k)}
            className={kind === k ? "h-7 rounded-md bg-ink px-2.5 text-small font-medium text-white" : "h-7 rounded-md border border-line-strong px-2.5 text-small text-ink-2 hover:bg-sunken"}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        <label className="flex flex-col gap-1 text-small text-ink-2">
          Time (patient local, YYYY-MM-DD HH:MM)
          <input value={time} onChange={(e) => setTime(e.target.value)} maxLength={16} className="h-8 rounded-md border border-line-strong px-2 text-body tnum" />
        </label>
        {glucose && (
          <div className="flex gap-2">
            <label className="flex flex-1 flex-col gap-1 text-small text-ink-2">
              Value
              <input value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" className="h-8 rounded-md border border-line-strong px-2 text-body tnum" />
            </label>
            <label className="flex flex-col gap-1 text-small text-ink-2">
              Unit
              <select value={unit} onChange={(e) => setUnit(e.target.value)} className="h-8 rounded-md border border-line-strong bg-surface px-2 text-body">
                <option>mg/dL</option>
                <option>mmol/L</option>
              </select>
            </label>
          </div>
        )}
        {kind === "medication" && (
          <label className="flex flex-col gap-1 text-small text-ink-2">
            Route
            <select value={column} onChange={(e) => setColumn(e.target.value)} className="h-8 rounded-md border border-line-strong bg-surface px-2 text-body">
              <option value="insulin_sc">Subcutaneous insulin</option>
              <option value="oral_agents">Non-insulin agent (oral / injectable)</option>
            </select>
          </label>
        )}
        {!glucose && (
          <label className="flex flex-col gap-1 text-small text-ink-2">
            {kind === "meal" ? "Description (optional)" : "Drug and dose as administered"}
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={200}
              placeholder={kind === "meal" ? "e.g. breakfast" : "e.g. insulin aspart 6u"}
              className="h-8 rounded-md border border-line-strong px-2 text-body"
            />
          </label>
        )}
        <Button variant="primary" disabled={busy || !ready} onClick={() => void submit()}>
          Add to twin
        </Button>
        {msg && (
          <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "text-small text-ink-2" : "text-small text-error-ink"}>
            {msg.text}
          </p>
        )}
        <p className="text-[11px] text-ink-4">
          Observations must be later than the latest one in the twin (append-only). Each is validated by the same
          adapter as uploaded files; medication text is interpreted by the canonical parser, never guessed.
        </p>
      </div>
    </Panel>
  );
}

export function RemoveSession({ k }: { k: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex items-center gap-2">
      {error && <span className="text-small text-error-ink">{error}</span>}
      {confirm ? (
        <>
          <span className="text-small text-ink-2">Delete this session and its decision log?</span>
          <Button
            size="sm"
            onClick={async () => {
              try {
                await api.deleteSession(k);
                await qc.invalidateQueries({ queryKey: ["ward"] });
                router.push("/ward/");
              } catch (e) {
                setError(e instanceof ApiError ? e.message : "Unexpected error");
              }
            }}
          >
            Delete
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirm(false)}>
            Cancel
          </Button>
        </>
      ) : (
        <Button size="sm" variant="ghost" onClick={() => setConfirm(true)}>
          <Trash2 aria-hidden className="size-3.5" /> Remove session
        </Button>
      )}
    </div>
  );
}
