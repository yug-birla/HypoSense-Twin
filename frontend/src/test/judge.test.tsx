// Judge-readiness UI: SYNTHETIC data only. Every plain-language text must match the backend policy.
import * as RT from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import OverviewPage from "@/app/page";
import { PlainEvidence } from "@/components/evidence/PlainEvidence";
import { STATE_MEANING } from "@/lib/states";
import { STEPS } from "@/lib/demo";
import type { Evidence } from "@/lib/api";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/queries", () => ({
  useMeta: () => ({ data: { model_status: "DEVELOPMENT" } }),
  useConfirmatory: () => ({ data: { status: "PENDING" } }),
}));

function wrap(ui: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <RT.Provider>{ui}</RT.Provider>
    </QueryClientProvider>,
  );
}

describe("overview", () => {
  it("says what HypoSense is, that it is a prototype, and offers three ways in", () => {
    wrap(<OverviewPage />);
    expect(screen.getByRole("heading", { name: /HypoSense Twin/ })).toBeInTheDocument();
    expect(screen.getByText(/Research prototype · not clinically validated/)).toBeInTheDocument();
    for (const t of ["Guided demo (5 min)", "Explore the ward replay", "Add patient data"]) expect(screen.getByText(t)).toBeInTheDocument();
    expect(screen.getByText("PENDING")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bsafe\b/i); // never "safe"
  });
  it("separates observed, predicted and no-forecast states", () => {
    wrap(<OverviewPage />);
    const obs = screen.getByText("Observed now").closest("div")!.parentElement!;
    expect(within(obs).getByText("LOW NOW")).toBeInTheDocument();
    const pred = screen.getByText("Prediction for the next 60 minutes").closest("div")!.parentElement!;
    for (const s of ["ALERT", "WATCH", "NO ALERT"]) expect(within(pred).getByText(s)).toBeInTheDocument();
  });
});

describe("state meanings", () => {
  it("are faithful to the policy: LOW NOW observed, ALERT predicted and not a confirmed low", () => {
    expect(STATE_MEANING.LOW_NOW.kind).toBe("observed");
    expect(STATE_MEANING.LOW_NOW.text).toMatch(/below 70 mg\/dL/);
    expect(STATE_MEANING.ALERT.kind).toBe("predicted");
    expect(STATE_MEANING.ALERT.text).toMatch(/not necessarily low now/);
    expect(STATE_MEANING.NO_ALERT.text).toMatch(/not a guarantee/);
    expect(STATE_MEANING.INSUFFICIENT_DATA.kind).toBe("unavailable");
    for (const m of Object.values(STATE_MEANING)) expect(m.text).not.toMatch(/dose|insulin units|treat with|safe/i);
  });
});

describe("guided demo", () => {
  it("has 8 honest steps that drive the real replay", () => {
    expect(STEPS).toHaveLength(8);
    expect(STEPS.some((s) => /Nothing is staged/.test(s.body))).toBe(true);
    expect(STEPS.some((s) => /whichever way it turned out/.test(s.body))).toBe(true);
    expect(STEPS.map((s) => s.action).filter(Boolean)).toEqual([
      "Start the replay",
      "Advance 2 hours",
      "Fast-forward to the first alert",
      "Advance 75 minutes",
    ]);
  });
});

describe("plain evidence", () => {
  const ev = {
    task: { horizon_min: 60 },
    confirmatory: "PENDING (sealed evaluation partition not opened)",
    ladder: { treated: { patients: 22, episodes: 56, models: { M2: { sens_at_1fa: 0.875, sens_at_1fa_ci95: [0.78, 1] }, M3: { sens_at_1fa: 0.911, sens_at_1fa_ci95: [0.79, 1] } } } },
    comparisons: { "preview_M3-M2:sens1": { point: 0.036, ci95: [-0.042, 0.088] } },
  } as unknown as Evidence;
  it("quotes the canonical numbers and says no reliable difference when the interval includes zero", () => {
    wrap(<PlainEvidence ev={ev} confirmatory={ev.confirmatory} />);
    expect(screen.getByText(/87.5% \(M2\) and 91.1% \(M3\) of 56 low episodes in 22 treated/)).toBeInTheDocument();
    expect(screen.getByText("no reliable difference yet")).toBeInTheDocument();
    expect(screen.getByText(/No — PENDING/)).toBeInTheDocument();
  });
});
