import * as RT from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import type { ReactNode } from "react";
import { Banner } from "@/components/evidence/Banner";
import { runs, withGaps } from "@/components/patient/GlucoseChart";
import { AckPanel, PatientHeader } from "@/components/patient/Panels";
import { InfoTag, QualityBadge, StatePill } from "@/components/ui/primitives";
import { WardTable } from "@/components/ward/WardTable";
import type { Evidence, TimelinePoint } from "@/lib/api";
import { bedLabel, clock } from "@/lib/format";
import { STATE } from "@/lib/states";
import { parseMessage, queriesFor } from "@/lib/stream";
import { bed, patient } from "./fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RT.Provider>{ui}</RT.Provider>
    </QueryClientProvider>,
  );
}

describe("policy state rendering", () => {
  it.each(Object.entries(STATE))("%s has a text label and an icon (never colour alone)", (state, style) => {
    const { container } = render(<StatePill state={state} />);
    expect(screen.getByText(style.label)).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.querySelector(`[data-state="${state}"]`)).not.toBeNull();
  });
  it("an unknown state renders as SYSTEM ERROR, never as a reassuring state", () => {
    render(<StatePill state="SOMETHING_NEW" />);
    expect(screen.getByText("SYSTEM ERROR")).toBeInTheDocument();
  });
  it("quality badges and info tags use readable text", () => {
    render(
      <>
        <QualityBadge code="SENSOR_FAULT_SUSPECTED" />
        <QualityBadge code="INPUT_REJECTED" />
        <InfoTag tag="MED_TIMING_UNKNOWN:insulin" />
      </>,
    );
    expect(screen.getByText("Sensor fault suspected")).toBeInTheDocument();
    expect(screen.getByText("Input rejected")).toBeInTheDocument();
    expect(screen.getByText("Timing unknown: insulin")).toBeInTheDocument();
  });
});

describe("ward board", () => {
  it("renders backend order, states, sensor fault, stale data and no-forecast states", () => {
    const beds = [
      bed({
        rank: 1,
        recording_key: "9001_0_20200101",
        cgm_mgdl: 39.6,
        cgm_low: true,
        decision: { ...bed().decision, state: "LOW_NOW", p: null, p_text: null, reasons: ["CGM_LOW", "SENSOR_FAULT_SUSPECTED"] },
        reason: "Sensor fault suspected: verify sensor and capillary glucose",
        badges: ["SENSOR_FAULT_SUSPECTED"],
      }),
      bed({ rank: 2, recording_key: "9002_0_20200101", decision: { ...bed().decision, state: "ALERT", p: 0.2, p_text: "20%" }, unacknowledged_notifications: 2 }),
      bed({ rank: 3, recording_key: "9003_0_20200101", data_age_s: 1800, stale: true, decision: { ...bed().decision, state: "INSUFFICIENT_DATA", p: null, p_text: null } }),
      bed({ rank: 4, recording_key: "9004_0_20200101", badges: ["INPUT_REJECTED"], decision: { ...bed().decision, state: "SYSTEM_ERROR", p: null, p_text: null } }),
    ];
    wrap(<WardTable beds={beds} offsetS={0} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[1]!.textContent)).toEqual(["9001 · R0", "9002 · R0", "9003 · R0", "9004 · R0"]);
    expect(within(rows[0]!).getByText("LOW NOW")).toBeInTheDocument();
    expect(within(rows[0]!).getAllByText("Sensor fault suspected").length).toBeGreaterThan(0);
    expect(within(rows[1]!).getByText("20%")).toBeInTheDocument();
    expect(within(rows[1]!).getByLabelText("2 unacknowledged notifications")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("no forecast")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("30 min ago")).toHaveClass("text-alert-ink");
    expect(within(rows[3]!).getByText("SYSTEM ERROR")).toBeInTheDocument();
    expect(within(rows[3]!).getAllByText("Input rejected").length).toBeGreaterThan(0);
  });
});

describe("patient review", () => {
  it("header shows a current low unmistakably and no probability when there is no forecast", () => {
    const v = patient({ current: { ...bed().decision, state: "LOW_NOW", p: null, p_text: null }, cgm_mgdl: 61.2, cgm_low: true });
    wrap(<PatientHeader v={v} offsetS={0} />);
    expect(screen.getByText("LOW NOW")).toBeInTheDocument();
    expect(screen.getByText("no forecast in this state")).toBeInTheDocument();
    expect(screen.getByText("61")).toHaveClass("text-low-ink");
  });
  it("acknowledgement offers exactly four reasons and needs an explicit choice", () => {
    wrap(<AckPanel v={patient()} offsetS={0} />);
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge…" }));
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(4);
    const record = screen.getByRole("button", { name: "Record acknowledgement" });
    expect(record).toBeDisabled();
    fireEvent.click(radios[0]!);
    expect(record).toBeEnabled();
    expect(screen.queryByRole("textbox")).toBeNull(); // no free text
  });
});

describe("evidence honesty", () => {
  it("development evidence is labelled and the sealed partition is stated", () => {
    render(<Banner ev={{ status: "DEVELOPMENT", confirmatory: "PENDING (sealed evaluation partition not opened)" } as Evidence} />);
    expect(screen.getByText(/DEVELOPMENT evidence/i)).toBeInTheDocument();
    expect(screen.getByText(/Evaluation partition remains sealed/)).toBeInTheDocument();
    expect(screen.getByText(/Not clinically validated/)).toBeInTheDocument();
  });
});

describe("stream contract", () => {
  it("ignores unknown versions and malformed data", () => {
    expect(parseMessage('{"v":2,"type":"decision"}')).toBeNull();
    expect(parseMessage("not json")).toBeNull();
    expect(parseMessage('{"v":1,"type":"bed_state"}')?.type).toBe("bed_state");
  });
  it("messages only trigger refetches of canonical snapshots", () => {
    expect(queriesFor({ v: 1, type: "bed_state" })).toEqual([["ward"], ["patient"]]);
    expect(queriesFor({ v: 1, type: "tick" })).toEqual([["status"]]);
    expect(queriesFor({ v: 1, type: "unknown" })).toEqual([]);
  });
});

describe("chart helpers (display only)", () => {
  const p = (ts: number, extra: Partial<TimelinePoint> = {}): TimelinePoint => ({
    decision_id: `x@${ts}`,
    ts,
    cgm_mgdl: 100,
    state: "NO_ALERT",
    p: 0.01,
    notify: false,
    in_episode: false,
    sensor_fault: false,
    exposure: {},
    ...extra,
  });
  it("breaks the CGM line at gaps > 20 min and never interpolates", () => {
    const out = withGaps([p(0), p(900), p(900 + 1500), p(900 + 1500 + 900)]);
    expect(out).toEqual([[0, 100], [900, 100], [901, null], [2400, 100], [3300, 100]]);
  });
  it("turns backend flags into contiguous regions", () => {
    const pts = [p(0), p(900, { in_episode: true }), p(1800, { in_episode: true }), p(2700), p(3600, { in_episode: true })];
    expect(runs(pts, (x) => x.in_episode)).toEqual([[900, 1800], [3600, 3600]]);
  });
  it("formats the record's local clock and pseudonymous labels", () => {
    expect(clock(0, 8 * 3600)).toBe("08:00");
    expect(bedLabel("2001_1_20201117")).toBe("2001 · R1");
  });
});

const wordRe = (word: string) => new RegExp(`\\b${word}\\b`, "i"); // regex word boundary

describe("prohibited wording (Blueprint §16.3)", () => {
  it("the word matcher works (positive and negative controls)", () => {
    expect(wordRe("safe").test("this is safe here")).toBe(true);
    expect(wordRe("safe").test("Leakage safeguards")).toBe(false);
    expect(wordRe("inject").test("inject now")).toBe(true);
  });
  const files: string[] = [];
  const walk = (d: string) => {
    for (const f of readdirSync(d)) {
      const full = path.join(d, f);
      if (statSync(full).isDirectory()) walk(full);
      else if (/\.tsx?$/.test(f) && !f.endsWith(".test.tsx") && !f.endsWith(".d.ts") && !full.includes(`${path.sep}test${path.sep}`)) files.push(full);
    }
  };
  walk(path.resolve(__dirname, ".."));
  it.each(["safe", "inject", "injection", "administer", "increase insulin", "reduce insulin", "give glucose", "units of"])("UI source never says %s", (word) => {
    for (const f of files) {
      const strings = readFileSync(f, "utf-8").match(/(["'`])(?:(?!\1).)*\1|>[^<{}]+</g) ?? [];
      const re = wordRe(word); // whole words: "safeguards" is not "safe"
      for (const s of strings) expect(re.test(s) ? `${f}: ${s}` : "").toBe("");
    }
  });
});

describe("P-B12 removal (DEC-2026-10-19-M)", () => {
  it("LOW_CONFIDENCE has no display mapping and is not a quality badge", async () => {
    const { BADGE_TEXT, tagText } = await import("@/lib/states");
    expect(Object.keys(BADGE_TEXT)).not.toContain("LOW_CONFIDENCE");
    expect(tagText("MED_TIMING_UNKNOWN:insulin")).toBe("Timing unknown: insulin");
    expect(tagText("EVENT_REJECTED")).toBe("Recent input rejected");
    expect(tagText("LOW_CONFIDENCE")).toBe("LOW_CONFIDENCE"); // no display text (backend never emits it)
  });
});
