"use client";
// Guided demo: a narrated tour that drives the REAL deterministic replay through the normal API
// (select, advance, advance-until-notification). It never fabricates events, never chooses a
// case by outcome and never touches E: the alert shown is simply the first notification in the
// fixed replay order of the default tuning-partition recordings.
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import { clock } from "./format";
import { useDataOffset } from "./queries";

const DEFAULT_CASES = 8; // same default as the Ward case picker (catalogue order, not performance)
const KEY = "hyposense.demo";

interface Persisted {
  active: boolean;
  step: number;
  alertKey: string | null;
  alertTs?: number | null;
  message: string | null;
}

export interface DemoStep {
  title: string;
  body: string;
  action?: string; // button label; the step's real operation
}

export const STEPS: DemoStep[] = [
  {
    title: "Meet the digital twin",
    body: "HypoSense reads CGM glucose, recorded medicines and patient context. For each patient it keeps a twin — an up-to-date picture of recent glucose, estimated medicine activity and data quality — and estimates the risk that a new CGM-detected low begins within the next 60 minutes.",
  },
  {
    title: "Start a ward replay",
    body: "We replay 8 real recordings from the development data (the default first 8 in catalogue order — not picked for good results). The sealed evaluation data are never shown.",
    action: "Start the replay",
  },
  {
    title: "Watch readings arrive",
    body: "Every CGM reading updates that patient's twin; the board re-sorts so the patients who need attention come first. States are decided by fixed rules on the server, never in the browser.",
    action: "Advance 2 hours",
  },
  {
    title: "See a real alert",
    body: "We fast-forward the replay until the first ALERT notification happens in any of the 8 patients. Nothing is staged: it is simply the first one in time order.",
    action: "Fast-forward to the first alert",
  },
  {
    title: "Why is HypoSense showing this?",
    body: "The state comes with a plain reason and the groups of information most associated with the estimate (glucose level, glucose history, medicine activity, context). These are statistical associations, not causes.",
  },
  {
    title: "Recorded vs estimated medicine",
    body: "Bars are doses as recorded. The shaded curves are a model-based estimate of how much recorded medicine may still be active — not a measured blood level.",
  },
  {
    title: "What happened afterward?",
    body: "We advance 75 minutes so the 60-minute window after the alert is complete. The history then shows whether a CGM low actually followed — whichever way it turned out. False and missed alerts are shown just as clearly as correct ones.",
    action: "Advance 75 minutes",
  },
  {
    title: "How was it tested?",
    body: "The Evidence page explains, in plain language first, how the models were developed and compared, what the development results suggest, and what is still pending: the final sealed evaluation has not been run.",
  },
];

interface DemoApi extends Persisted {
  busy: boolean;
  error: string | null;
  done: boolean[]; // per step: action completed (or no action)
  start: () => void;
  exit: () => void;
  go: (step: number) => void;
  run: () => Promise<void>;
}

const Ctx = createContext<DemoApi | null>(null);

function load(): Persisted {
  try {
    const v = JSON.parse(sessionStorage.getItem(KEY) ?? "null") as Persisted | null;
    if (v && typeof v.step === "number") return v;
  } catch {
    /* storage unavailable: start fresh */
  }
  return { active: false, step: 0, alertKey: null, message: null };
}

export function DemoProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const qc = useQueryClient();
  const offset = useDataOffset();
  const [st, setSt] = useState<Persisted>({ active: false, step: 0, alertKey: null, message: null });
  const [done, setDone] = useState<boolean[]>(STEPS.map((s) => !s.action));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setSt(load()), []);
  useEffect(() => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(st));
    } catch {
      /* ignore */
    }
  }, [st]);

  const show = useCallback(
    (step: number, alertKey: string | null) => {
      const patient = (tab: string) => (alertKey ? `/patient/?key=${encodeURIComponent(alertKey)}&tab=${tab}` : "/ward/");
      const target: Record<number, [string, string | null]> = {
        0: ["/", "how"],
        1: ["/ward/", null],
        2: ["/ward/", null],
        3: [patient("overview"), null],
        4: [patient("explain"), "why"],
        5: [patient("medications"), "medication"],
        6: [patient("history"), "history"],
        7: ["/evidence/", null],
      };
      const [href, anchor] = target[step] ?? ["/", null];
      router.push(href);
      if (anchor) setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" }), 600);
    },
    [router],
  );

  const go = useCallback(
    (step: number) => {
      const s = Math.max(0, Math.min(STEPS.length - 1, step));
      setError(null);
      setSt((p) => ({ ...p, step: s, message: null }));
      show(s, st.alertKey);
    },
    [show, st.alertKey],
  );

  const refresh = useCallback(() => {
    for (const k of ["status", "ward", "patient"]) void qc.invalidateQueries({ queryKey: [k] });
  }, [qc]);

  const run = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      let message: string | null = null;
      let alertKey = st.alertKey;
      let alertTs = st.alertTs ?? null;
      if (st.step === 1) {
        const cases = await api.cases();
        await api.select(cases.slice(0, DEFAULT_CASES).map((c) => c.recording_key));
        message = `Replay started for ${Math.min(DEFAULT_CASES, cases.length)} recorded patients, each from the start of its recording.`;
        alertKey = null;
      } else if (st.step === 2) {
        await api.advance(7200);
        message = "Two hours of recorded readings have been processed.";
      } else if (st.step === 3) {
        const ev = await api.advanceUntilNotification();
        if (ev.found && ev.recording_key) {
          alertKey = ev.recording_key;
          alertTs = ev.ts;
          message = `First ALERT in the replay: ${ev.recording_key.split("_")[0]} at ${clock(ev.ts ?? 0, offset)} (record clock), estimated risk ${ev.p_text}. Glucose is not necessarily low yet — this is a forecast.`;
        } else {
          message = "No ALERT notification occurred in these recordings. The demo continues with the ward as it is.";
        }
      } else if (st.step === 6) {
        await api.advance(4500);
        message = "75 more minutes processed.";
        if (alertKey && alertTs !== null) {
          const v = await api.patient(alertKey);
          const row = v.ledger_entries.find((e) => e.forecast_ts === alertTs);
          const when = clock(alertTs, offset);
          const outcome =
            row?.outcome === "LOW_FOLLOWED"
              ? "a CGM-detected low DID follow within 60 minutes (a correct early warning)"
              : row?.outcome === "NO_LOW"
                ? "NO CGM-detected low followed within 60 minutes (a false alert)"
                : row?.outcome === "OUTCOME_UNKNOWN"
                  ? "the outcome is unknown (the recording ended)"
                  : "the outcome is not available yet";
          message = `The ${when} alert: ${outcome}. Find the ${when} row in the history below. Later alerts may still be waiting for their own 60 minutes.`;
        }
      }
      refresh();
      setDone((d) => d.map((v, i) => (i === st.step ? true : v)));
      setSt((p) => ({ ...p, alertKey, alertTs, message }));
      show(st.step, alertKey);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The step could not be completed.");
    } finally {
      setBusy(false);
    }
  }, [st.step, st.alertKey, offset, refresh, show]);

  const value = useMemo<DemoApi>(
    () => ({
      ...st,
      busy,
      error,
      done,
      start: () => {
        setDone(STEPS.map((s) => !s.action));
        setSt({ active: true, step: 0, alertKey: null, message: null });
        show(0, null);
      },
      exit: () => setSt((p) => ({ ...p, active: false })),
      go,
      run,
    }),
    [st, busy, error, done, go, run, show],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDemo(): DemoApi {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDemo outside DemoProvider");
  return v;
}
