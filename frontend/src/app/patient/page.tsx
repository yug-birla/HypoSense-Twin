"use client";
import clsx from "clsx";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { ApiError } from "@/lib/api";
import { bedLabel } from "@/lib/format";
import { lastPatient } from "@/lib/lastPatient";
import { useConnectionLost, useDataOffset, useMeta, usePatient, useWard } from "@/lib/queries";
import { PageHeader } from "@/components/shell/AppShell";
import { ReplayBar } from "@/components/replay/ReplayBar";
import { ExposureChart } from "@/components/patient/ExposureChart";
import { GlucoseChart } from "@/components/patient/GlucoseChart";
import { AckPanel, LedgerPanel } from "@/components/patient/Panels";
import { BackToWard, DataQualityCard, Explainability, ProfileCard, RecentMedication, RecentReadings, StatusRail, TwinAnatomy } from "@/components/patient/Twin";
import { Details, Empty, ErrorBox, Panel, Skeleton, StatePill } from "@/components/ui/primitives";
import { ObservationPanel, RemoveSession, SessionBanner } from "@/components/intake/SessionPanels";
import { AskPanel } from "@/components/patient/AskPanel";

const TABS = [
  ["overview", "Overview"],
  ["medications", "Medications"],
  ["twin", "Twin anatomy"],
  ["explain", "Explainability"],
  ["history", "History & alerts"],
] as const;
type Tab = (typeof TABS)[number][0];

function Chooser({ tab }: { tab: string | null }) {
  const ward = useWard();
  const title = tab === "twin" ? "Twin anatomy" : tab === "explain" ? "Explainability" : "Patient review";
  return (
    <div>
      <PageHeader title={title} sub="Choose a patient from the current replay or a new-data session." bubble="Pick anyone on the board to look inside their twin." />
      <div className="p-6">
        {!ward.data?.beds.length ? (
          <Panel>
            <Empty title="No patient on the board">
              Start a replay in the <Link className="text-accent underline" href="/replay/">Replay studio</Link> or on the{" "}
              <Link className="text-accent underline" href="/ward/">Ward board</Link>, or <Link className="text-accent underline" href="/intake/">add a patient</Link>.
            </Empty>
          </Panel>
        ) : (
          <Panel title="Patients">
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-2">
              {ward.data.beds.map((b) => (
                <li key={b.recording_key}>
                  <Link
                    href={`/patient/?key=${encodeURIComponent(b.recording_key)}${tab ? `&tab=${tab}` : ""}`}
                    className="flex items-center justify-between rounded-2xl border border-line bg-surface px-4 py-3 hover:border-accent"
                  >
                    <span className="font-semibold text-ink">{bedLabel(b.recording_key, b.label)}</span>
                    <StatePill state={b.decision.state} size="sm" />
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  );
}

function Review({ k, tab }: { k: string; tab: Tab }) {
  const q = usePatient(k);
  const meta = useMeta();
  const offset = useDataOffset();
  const lost = useConnectionLost();
  const router = useRouter();
  const th = meta.data?.thresholds;
  useEffect(() => lastPatient.set(k), [k]);
  const setTab = (t: string) => router.push(`/patient/?key=${encodeURIComponent(k)}&tab=${t}`);
  if (q.isError) {
    const nf = q.error instanceof ApiError && (q.error.status === 404 || q.error.status === 409);
    return (
      <div className="p-6">
        <ErrorBox
          title={nf ? "This bed is not in the current replay or a new-data session" : "Patient view unavailable"}
          detail={nf ? "Select a bed from the Ward board." : (q.error as Error).message}
          onRetry={nf ? undefined : () => q.refetch()}
        />
      </div>
    );
  }
  if (lost) {
    return (
      <div className="p-6">
        <ErrorBox title="Patient state not current" detail="The service or stream is unreachable; the view is hidden until it reconnects." />
      </div>
    );
  }
  if (!q.data) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  const v = q.data;
  const live = v.source === "NEW_DATA_SESSION";
  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <BackToWard />
        {live ? <RemoveSession k={v.recording_key} /> : null}
      </div>
      {live ? <SessionBanner v={v} /> : <ReplayBar compact />}
      <ProfileCard v={v} />
      <div role="tablist" aria-label="Patient views" className="flex flex-wrap gap-2">
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
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div role="tabpanel" aria-label={TABS.find((t) => t[0] === tab)?.[1]} className="flex min-w-0 flex-col gap-4">
          {tab === "overview" && (
            <>
              {live && <ObservationPanel key={v.recording_key} v={v} offsetS={offset} />}
              <Panel title="Glucose timeline and risk (last 24 hours)">
                <GlucoseChart view={v} offsetS={offset} tauAlert={th?.tau_alert ?? null} tauWatch={th?.tau_watch ?? null} gapS={meta.data?.policy.max_gap_s} />
                <Details summary="How to read this chart">
                  <ul className="flex list-disc flex-col gap-1 pl-4">
                    <li><b>Violet line</b>: observed CGM glucose. Gaps longer than 20 minutes are not joined.</li>
                    <li><b>Green band</b>: 70–180 mg/dL. <b>Red dashed line</b>: 70 mg/dL (low); dotted: 54 mg/dL.</li>
                    <li><b>Red shading</b>: CGM-detected low episodes. <b>Triangles</b>: alert notifications.</li>
                    <li><b>Lower panel (pink line)</b>: the model’s estimated risk — a prediction — with the alert and watch thresholds.</li>
                    <li><b>Bars and dots</b>: recorded doses and meals. The chip buttons above turn layers on or off.</li>
                  </ul>
                </Details>
              </Panel>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                <RecentReadings v={v} offsetS={offset} />
                <RecentMedication v={v} offsetS={offset} />
                <DataQualityCard v={v} />
              </div>
            </>
          )}
          {tab === "medications" && (
            <>
              <Panel id="medication" title="Medicines: recorded doses and estimated activity" aside={<span className="text-[11px] text-ink-4">bars = recorded · curves = model estimate</span>}>
                <ExposureChart view={v} offsetS={offset} />
                <p className="mt-2 text-small text-ink-3">
                  <b className="font-medium text-ink-2">Recorded</b>: doses as entered in the record. <b className="font-medium text-ink-2">Estimated</b>: how much of
                  the recorded medicine may still be active, from fixed population-level time profiles. It is not a measured blood level, and it is
                  never used to suggest a dose.
                </p>
              </Panel>
              <RecentMedication v={v} offsetS={offset} />
            </>
          )}
          {tab === "twin" && <TwinAnatomy v={v} offsetS={offset} />}
          {tab === "explain" && (
            <>
              <Explainability v={v} tauAlert={th?.tau_alert} tauWatch={th?.tau_watch} />
              <AskPanel k={v.recording_key} />
            </>
          )}
          {tab === "history" && (
            <>
              <AckPanel v={v} offsetS={offset} />
              <LedgerPanel v={v} offsetS={offset} />
            </>
          )}
        </div>
        <div className="order-first xl:order-none">
          <StatusRail v={v} offsetS={offset} onTab={setTab} />
        </div>
      </div>
      <p className="text-[12px] text-ink-4">{v.caveat} No dose or treatment recommendation is made.</p>
    </div>
  );
}

function Inner() {
  const params = useSearchParams();
  const key = params.get("key");
  const raw = params.get("tab");
  const tab = (TABS.some((t) => t[0] === raw) ? raw : "overview") as Tab;
  return key ? <Review k={key} tab={tab} /> : <Chooser tab={raw} />;
}

export default function PatientPage() {
  return (
    <Suspense>
      <Inner />
    </Suspense>
  );
}
