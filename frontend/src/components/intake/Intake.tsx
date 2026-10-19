"use client";
// Add patient / import data. Every check, question and parse happens on the server (intake
// module, canonical adapter); this page only displays the draft and sends the user's answers.
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, FileUp, Info, UserPlus, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type IntakeDraft, type IntakeFinding, type IntakeQuestion } from "@/lib/api";
import { Button, ErrorBox, Panel, StatusTag } from "@/components/ui/primitives";

const LABEL_RE = /^[A-Za-z0-9 _-]{0,24}$/;
const STATUS_TEXT: Record<string, { tone: "ok" | "warn" | "dev"; text: string }> = {
  READY: { tone: "ok", text: "Ready to create" },
  NEEDS_ANSWERS: { tone: "dev", text: "Questions need an answer" },
  BLOCKED: { tone: "warn", text: "Cannot be accepted yet" },
};

function errText(e: unknown): string {
  return e instanceof ApiError ? e.message : "Unexpected error";
}

async function toBase64(file: File): Promise<string> {
  const buf = new Uint8Array(await file.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(bin);
}

function Start({ onDraft }: { onDraft: (d: IntakeDraft) => void }) {
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const labelOk = LABEL_RE.test(label);
  const run = async (fn: () => Promise<IntakeDraft>) => {
    setBusy(true);
    setError(null);
    try {
      onDraft(await fn());
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };
  const upload = async (f: File) => {
    if (f.size > 5_000_000) return setError("The file exceeds 5 MB.");
    await run(async () => api.intakeUpload(f.name, await toBase64(f), label.trim() || null));
  };
  return (
    <div className="flex flex-col gap-4">
      <Panel title="Label (optional)">
        <label className="flex max-w-md flex-col gap-1 text-small text-ink-2">
          Display label for this patient
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            maxLength={24}
            placeholder="e.g. Bed 4 or SYNTHETIC-demo"
            aria-invalid={!labelOk}
            className="h-8 rounded-md border border-line-strong px-2 text-body"
          />
        </label>
        <p className={clsx("mt-1 text-[11.5px]", labelOk ? "text-ink-4" : "text-error-ink")}>
          Letters, digits, spaces, - and _ only. Do not enter names, record numbers or contact details; the
          system assigns its own identifier.
        </p>
      </Panel>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Upload a file">
          <p className="text-small text-ink-2">
            CSV (UTF-8) or XLSX with one worksheet and a header row: date/time, CGM glucose, and optionally capillary
            glucose, meals and medication entries. Up to 5 MB.
          </p>
          <input
            ref={file}
            type="file"
            accept=".csv,.xlsx"
            className="sr-only"
            aria-label="Recording file"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void upload(f);
              e.target.value = "";
            }}
          />
          <Button variant="primary" className="mt-3" disabled={busy || !labelOk} onClick={() => file.current?.click()}>
            <FileUp aria-hidden className="size-4" /> Choose file…
          </Button>
        </Panel>
        <Panel title="Or start without a file">
          <p className="text-small text-ink-2">
            Create an empty twin and add CGM readings, capillary glucose, meals and medication one at a time. A forecast
            appears only once enough recent CGM history exists.
          </p>
          <Button className="mt-3" disabled={busy || !labelOk} onClick={() => void run(() => api.intakeNew(label.trim() || null))}>
            <UserPlus aria-hidden className="size-4" /> Start new patient
          </Button>
        </Panel>
      </div>
      {error && <ErrorBox title="Not accepted" detail={error} />}
    </div>
  );
}

function FindingIcon({ f }: { f: IntakeFinding }) {
  const cls = "mt-0.5 size-4 shrink-0";
  if (f.severity === "blocking") return <XCircle aria-label="blocking" className={clsx(cls, "text-error-ink")} />;
  if (f.severity === "warning") return <AlertTriangle aria-label="warning" className={clsx(cls, "text-watch-ink")} />;
  return <Info aria-label="information" className={clsx(cls, "text-ink-4")} />;
}

function Findings({ items }: { items: IntakeFinding[] }) {
  if (!items.length) return <p className="text-small text-ink-3">No validation findings.</p>;
  const order = { blocking: 0, warning: 1, info: 2 } as Record<string, number>;
  return (
    <ul className="flex flex-col gap-1.5">
      {[...items]
        .sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3))
        .map((f, i) => (
          <li key={`${f.code}-${i}`} className="flex items-start gap-2 text-small">
            <FindingIcon f={f} />
            <span className="text-ink-2">
              {f.message}
              {f.count > 1 && <span className="ml-1 text-ink-4 tnum">({f.count.toLocaleString()} rows)</span>}
            </span>
          </li>
        ))}
    </ul>
  );
}

function QuestionRow({ q, onAnswer, busy }: { q: IntakeQuestion; onAnswer: (v: string) => void; busy: boolean }) {
  const [text, setText] = useState(q.answer?.startsWith("replace:") ? q.answer.slice(8) : "");
  const id = `q-${q.id.replace(/[^A-Za-z0-9]/g, "_")}`;
  const answered = q.answer !== null && q.answer !== undefined;
  return (
    <li className="flex flex-col gap-1.5 border-b border-line py-3 last:border-b-0">
      <div className="flex items-start gap-2">
        {answered ? (
          <CheckCircle2 aria-label="answered" className="mt-0.5 size-4 shrink-0 text-accent" />
        ) : (
          <span aria-hidden className={clsx("mt-1.5 size-2 shrink-0 rounded-full", q.required ? "bg-watch" : "bg-line-strong")} />
        )}
        <div className="min-w-0 flex-1">
          <label htmlFor={id} className="text-body font-medium text-ink">
            {q.prompt}
            <span className="ml-2 text-[10.5px] font-semibold uppercase tracking-wide text-ink-4">
              {q.required ? "required" : "optional"}
            </span>
          </label>
          <p className="text-[11.5px] text-ink-3">
            <span className="font-medium text-ink-2">Why we ask:</span> {q.reason}
            {q.impact && (
              <>
                {" "}
                <span className="font-medium text-ink-2">If you can’t answer:</span> {q.impact}
              </>
            )}
          </p>
        </div>
      </div>
      <div className="ml-6 flex flex-wrap items-center gap-2">
        {q.kind === "choice" ? (
          <select
            id={id}
            disabled={busy}
            value={q.answer ?? ""}
            onChange={(e) => onAnswer(e.target.value)}
            className="h-8 max-w-full rounded-md border border-line-strong bg-surface px-2 text-body"
          >
            <option value="">{q.suggested ? "Choose… (suggestion marked)" : "Choose…"}</option>
            {q.options.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
                {v === q.suggested ? "  (suggested from the header)" : ""}
              </option>
            ))}
          </select>
        ) : (
          <>
            <input
              id={id}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. insulin aspart 6u"
              maxLength={200}
              className="h-8 w-72 rounded-md border border-line-strong px-2 text-body"
            />
            <Button size="sm" disabled={busy || !text.trim()} onClick={() => onAnswer(`replace:${text.trim()}`)}>
              Use this entry
            </Button>
            {q.options.map(([v, l]) => (
              <Button key={v} size="sm" variant="ghost" disabled={busy} onClick={() => onAnswer(v)}>
                {l}
              </Button>
            ))}
          </>
        )}
        {answered && q.kind !== "choice" && (
          <span className="text-small text-ink-3">
            Answer: {q.answer === "keep" ? "kept as recorded" : q.answer?.slice(8)}
          </span>
        )}
      </div>
      {q.error && (
        <p role="alert" className="ml-6 text-small text-error-ink">
          Not accepted: {q.error}
        </p>
      )}
    </li>
  );
}

function ContextForm({ d, onSave, busy }: { d: IntakeDraft; onSave: (c: Record<string, string>) => void; busy: boolean }) {
  const [vals, setVals] = useState<Record<string, string>>(Object.fromEntries(d.context.map((c) => [c.name, c.value])));
  return (
    <Panel title="Patient context (optional)" aside={<span className="text-[11px] text-ink-4">Missing fields stay missing — never zero</span>}>
      <div className="grid grid-cols-1 gap-x-4 gap-y-2 md:grid-cols-3">
        {d.context.map((c) => (
          <label key={c.name} className="flex flex-col gap-1 text-small text-ink-2">
            {c.label}
            {c.name === "sex" ? (
              <select
                value={vals[c.name] ?? ""}
                onChange={(e) => setVals({ ...vals, [c.name]: e.target.value })}
                className="h-8 rounded-md border border-line-strong bg-surface px-2 text-body"
              >
                <option value="">Not stated</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
              </select>
            ) : (
              <input
                value={vals[c.name] ?? ""}
                onChange={(e) => setVals({ ...vals, [c.name]: e.target.value })}
                inputMode={c.name === "prescribed_agents" ? "text" : "decimal"}
                maxLength={200}
                placeholder={c.name === "prescribed_agents" ? "e.g. insulin glargine, metformin" : ""}
                className="h-8 rounded-md border border-line-strong px-2 text-body"
              />
            )}
          </label>
        ))}
      </div>
      <Button size="sm" className="mt-3" disabled={busy} onClick={() => onSave(vals)}>
        Validate context
      </Button>
    </Panel>
  );
}

function Preview({ d }: { d: IntakeDraft }) {
  if (!d.preview_headers.length) return null;
  return (
    <Panel title="Your file, as we read it" aside={<span className="text-[11px] text-ink-4">{d.file_name} · first rows</span>} bodyClass="p-0">
      <div className="overflow-x-auto">
        <table className="w-full text-small">
          <thead>
            <tr className="border-b border-line bg-sunken text-left">
              {d.preview_headers.map((h) => {
                const m = d.mapping.find((x) => x.header === h);
                return (
                  <th key={h} scope="col" className="px-3 py-2 align-bottom">
                    <span className="block font-mono text-[11px] text-ink-3">{h}</span>
                    <span className={clsx("block text-[11.5px] font-semibold", m?.canonical ? "text-ink" : "text-ink-4")}>
                      → {String(m?.label ?? "?")}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {d.preview.map((row, i) => (
              <tr key={i} className="border-b border-line last:border-b-0">
                {d.preview_headers.map((h) => (
                  <td key={h} className="whitespace-nowrap px-3 py-1.5 text-ink-2 tnum">
                    {(row[h] as string | null) ?? <span className="text-ink-4">—</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function Review({ d, setD, onReset }: { d: IntakeDraft; setD: (d: IntakeDraft) => void; onReset: () => void }) {
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const qc = useQueryClient();
  const call = async (fn: () => Promise<IntakeDraft>) => {
    setBusy(true);
    setError(null);
    try {
      setD(await fn());
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };
  const commit = async () => {
    setCreating(true);
    setBusy(true);
    setError(null);
    try {
      const r = await api.intakeCommit(d.draft_id);
      await qc.invalidateQueries({ queryKey: ["ward"] });
      await qc.invalidateQueries({ queryKey: ["sessions"] });
      router.push(`/patient/?key=${encodeURIComponent(r.recording_key)}`);
    } catch (e) {
      setError(errText(e));
      setBusy(false);
      setCreating(false);
    }
  };
  const st = STATUS_TEXT[d.status] ?? { tone: "warn" as const, text: d.status };
  const required = d.questions.filter((q) => q.required);
  const optional = d.questions.filter((q) => !q.required);
  const s = d.summary as Record<string, number | string | null>;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface px-5 py-3">
        <span className="text-body font-semibold text-ink">
          {d.label ? `${d.label} · ` : ""}New patient {d.patient_id}
        </span>
        <StatusTag tone={st.tone}>{st.text}</StatusTag>
        {s.cgm_readings !== undefined && (
          <span className="text-small text-ink-3 tnum">
            {Number(s.cgm_readings).toLocaleString()} CGM readings
            {s.cgm_span_h ? ` over ${s.cgm_span_h} h` : ""}
            {s.meals ? ` · ${s.meals} meals` : ""}
            {s.medication_events ? ` · ${s.medication_events} medication entries` : ""}
            {s.capillary_readings ? ` · ${s.capillary_readings} capillary readings` : ""}
            {s.first_local ? ` · ${s.first_local} → ${s.last_local} (patient local time)` : ""}
          </span>
        )}
        <span className="ml-auto flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => {
              void api.intakeDiscard(d.draft_id).finally(onReset);
            }}
          >
            Discard
          </Button>
          <Button variant="primary" disabled={busy || d.status !== "READY"} onClick={() => void commit()} aria-label="Create patient twin">
            {creating ? "Building the twin… (a few seconds per week of data)" : "Create patient twin"}
          </Button>
        </span>
      </div>
      {error && <ErrorBox title="Not accepted" detail={error} />}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Panel title={`A few questions${d.questions.length ? ` (${d.questions.filter((q) => q.answer).length} of ${d.questions.length} answered)` : ""}`}>
          {!d.questions.length ? (
            <p className="text-small text-ink-3">Nothing needs clarifying — everything in the file was recognised.</p>
          ) : (
            <ul>
              {[...required, ...optional].map((q) => (
                <QuestionRow key={q.id} q={q} busy={busy} onAnswer={(v) => void call(() => api.intakeAnswer(d.draft_id, { [q.id]: v }, {}))} />
              ))}
            </ul>
          )}
          <p className="mt-2 text-[11.5px] text-ink-4">
            We only ask about things we found in your data. Nothing is guessed: units, clocks and medicine details come from
            the file or from your answers. Optional items left unanswered stay as recorded, and anything unknown is treated as
            unknown.
          </p>
        </Panel>
        <Panel title="What we found">
          <Findings items={d.findings} />
        </Panel>
      </div>
      <Preview d={d} />
      <ContextForm d={d} busy={busy} onSave={(c) => void call(() => api.intakeAnswer(d.draft_id, {}, c))} />
      <p className="text-[11.5px] text-ink-4">{d.notice}</p>
    </div>
  );
}

const STEPS = ["Add data", "Review what we found", "Answer a few questions", "Create the twin", "Explore the patient"];

function Stepper({ current }: { current: number }) {
  return (
    <ol aria-label="Progress" className="mb-4 flex flex-wrap items-center gap-x-2 gap-y-1">
      {STEPS.map((t, i) => (
        <li key={t} className="flex items-center gap-2" aria-current={i === current ? "step" : undefined}>
          <span
            className={clsx(
              "flex size-6 items-center justify-center rounded-full text-[12px] font-semibold",
              i < current ? "bg-accent text-white" : i === current ? "bg-ink text-white" : "bg-sunken text-ink-3",
            )}
          >
            {i < current ? "✓" : i + 1}
          </span>
          <span className={clsx("text-small", i === current ? "font-semibold text-ink" : "text-ink-3")}>{t}</span>
          {i < STEPS.length - 1 && <span aria-hidden className="mx-1 h-px w-6 bg-line-strong" />}
        </li>
      ))}
    </ol>
  );
}

export function IntakeFlow() {
  const [draft, setDraft] = useState<IntakeDraft | null>(null);
  const step = !draft ? 0 : draft.status === "READY" ? 3 : draft.questions.some((q) => q.required && !q.answer) ? 2 : 1;
  return (
    <>
      <Stepper current={step} />
      {draft ? <Review d={draft} setD={setDraft} onReset={() => setDraft(null)} /> : <Start onDraft={setDraft} />}
    </>
  );
}
