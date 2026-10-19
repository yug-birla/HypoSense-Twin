"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ApiError } from "@/lib/api";
import { bedLabel } from "@/lib/format";
import { useConnectionLost, useDataOffset, useMeta, usePatient, useWard } from "@/lib/queries";
import { PageHeader } from "@/components/shell/AppShell";
import { ReplayBar } from "@/components/replay/ReplayBar";
import { ExposureChart } from "@/components/patient/ExposureChart";
import { GlucoseChart } from "@/components/patient/GlucoseChart";
import { AckPanel, LedgerPanel, PatientHeader, QualityPanel, WhyPanel } from "@/components/patient/Panels";
import { Details, Empty, ErrorBox, Panel, Skeleton, StatePill } from "@/components/ui/primitives";
import { ObservationPanel, RemoveSession, SessionBanner } from "@/components/intake/SessionPanels";
import { AskPanel } from "@/components/patient/AskPanel";

function Chooser() {
  const ward = useWard();
  return (
    <div>
      <PageHeader title="Patient review" sub="Select a bed from the current replay or a new-data session." />
      <div className="p-6">
        {!ward.data?.beds.length ? (
          <Panel>
            <Empty title="No replay running">
              Start a ward replay on the <Link className="text-accent underline" href="/ward/">Ward board</Link>, or{" "}
              <Link className="text-accent underline" href="/intake/">add a patient</Link>.
            </Empty>
          </Panel>
        ) : (
          <Panel title="Beds" bodyClass="p-2">
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-1.5">
              {ward.data.beds.map((b) => (
                <li key={b.recording_key}>
                  <Link
                    href={`/patient/?key=${encodeURIComponent(b.recording_key)}`}
                    className="flex items-center justify-between rounded-md border border-line px-3 py-2 hover:bg-sunken"
                  >
                    <span className="font-medium">{bedLabel(b.recording_key, b.label)}</span>
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

function Review({ k }: { k: string }) {
  const q = usePatient(k);
  const meta = useMeta();
  const offset = useDataOffset();
  const lost = useConnectionLost();
  const th = meta.data?.thresholds;
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
      <nav aria-label="Breadcrumb" className="-mb-1 text-small text-ink-3">
        <Link href="/" className="hover:text-accent hover:underline">Ward board</Link>
        <span aria-hidden className="mx-1.5 text-ink-4">/</span>
        <span className="text-ink-2">{bedLabel(v.recording_key, v.label)}</span>
      </nav>
      {live ? (
        <div className="flex flex-col gap-2">
          <SessionBanner v={v} />
          <div className="flex justify-end">
            <RemoveSession k={v.recording_key} />
          </div>
        </div>
      ) : (
        <ReplayBar compact />
      )}
      <PatientHeader v={v} offsetS={offset} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-4">
          <h2 className="label-caps -mb-2 mt-1">How did we get here?</h2>
          <Panel title="Glucose over the last 24 hours">
            <GlucoseChart view={v} offsetS={offset} tauAlert={th?.tau_alert ?? null} tauWatch={th?.tau_watch ?? null} gapS={meta.data?.policy.max_gap_s} />
            <Details summary="How to read this chart">
              <ul className="flex list-disc flex-col gap-1 pl-4">
                <li><b>Black line</b>: observed CGM glucose. Gaps longer than 20 minutes are not joined.</li>
                <li><b>Green band</b>: 70–180 mg/dL. <b>Red dashed line</b>: 70 mg/dL (low); dotted: 54 mg/dL.</li>
                <li><b>Red shading</b>: CGM-detected low episodes. <b>Triangles</b>: alert notifications.</li>
                <li><b>Lower panel</b>: the model’s estimated risk (a prediction), with the alert and watch thresholds.</li>
                <li><b>Bars and dots</b>: recorded doses and meals. The chip buttons above turn layers on or off.</li>
              </ul>
            </Details>
          </Panel>
          <Panel
            id="medication"
            title="Medicines: recorded doses and estimated activity"
            aside={<span className="text-[11px] text-ink-4">Bars = recorded · curves = model estimate</span>}
          >
            <ExposureChart view={v} offsetS={offset} />
            <p className="mt-1 text-small text-ink-3">
              <b className="font-medium text-ink-2">Recorded</b>: doses as entered in the record. <b className="font-medium text-ink-2">Estimated</b>:
              how much of the recorded medicine may still be active, from fixed population-level time profiles. It is not a measured
              blood level, and it is never used to suggest a dose.
            </p>
          </Panel>
        </div>
        <div className="grid grid-cols-1 content-start gap-4 md:grid-cols-2 xl:grid-cols-1">
          {live && <ObservationPanel key={v.recording_key} v={v} offsetS={offset} />}
          <WhyPanel v={v} tauAlert={th?.tau_alert} tauWatch={th?.tau_watch} />
          <AckPanel v={v} offsetS={offset} />
          <AskPanel k={v.recording_key} />
          <QualityPanel v={v} />
        </div>
      </div>
      <LedgerPanel v={v} offsetS={offset} />
      <p className="text-[11.5px] text-ink-4">{v.caveat} No dose or treatment recommendation is made.</p>
    </div>
  );
}

function Inner() {
  const key = useSearchParams().get("key");
  return key ? <Review k={key} /> : <Chooser />;
}

export default function PatientPage() {
  return (
    <Suspense>
      <Inner />
    </Suspense>
  );
}
