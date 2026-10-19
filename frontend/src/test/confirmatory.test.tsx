import { render, screen } from "@testing-library/react";
import { ConfirmatoryPanel, type ConfirmatoryDoc } from "@/components/evidence/Confirmatory";

let doc: ConfirmatoryDoc | undefined;
vi.mock("@/lib/queries", () => ({
  useConfirmatory: () => ({ data: doc, isError: false, error: null, refetch: vi.fn() }),
}));

// SYNTHETIC documents: the panel copies numbers, it never computes them.
const result = (status: string, h1: boolean): ConfirmatoryDoc => ({
  status,
  run_id: "SYNTHETIC-RUN",
  results_sha256: "ab".repeat(32),
  freeze: { freeze_id: "F", record_sha256: "cd".repeat(32), source_commit: "c" },
  primary: { M2_sens_at_1fa: 0.8, M3_sens_at_1fa: 0.85, delta: 0.05, delta_ci95: [-0.02, 0.1], undefined_resamples: 0, g5_pass: true, h1_supported: h1 },
  ladder: { M2: { sens1: 0.8, sens1_ci95: [0.7, 0.9], logloss: 0.03 }, M3: { sens1: 0.85, sens1_ci95: [0.75, 0.95], logloss: 0.029 } },
  selection: { selected: "M3", steps: ["H1 not supported; M3 higher sens@1FA and log-loss not worse -> M3"] },
  interpretation: ["Δ point estimate > 0, CI includes 0; S3 favours M3"],
  analyses: [
    { key: "primary", group: "Primary", label: "E-treated", available: true, patients: 3, episodes: 9, M2_sens1: 0.8, M3_sens1: 0.85, delta: 0.05, delta_ci95: [-0.02, 0.1] },
    { key: "SA8", group: "Sensitivity", label: "SA8 without laboratory features", available: false },
  ],
});

describe("confirmatory panel", () => {
  it("shows PENDING and no numbers while E is sealed", () => {
    doc = { status: "PENDING", note: "The sealed evaluation partition (E) has not been opened." };
    const { container } = render(<ConfirmatoryPanel />);
    expect(screen.getByText("Confirmatory result: PENDING")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\d+\.\d %/);
  });
  it("shows the frozen result, H1 verdict and missing analyses as missing", () => {
    doc = result("CONFIRMATORY", false);
    render(<ConfirmatoryPanel />);
    expect(screen.getByText("H1 not supported")).toBeInTheDocument();
    expect(screen.getAllByText("+5.0 pp").length).toBeGreaterThan(0);
    expect(screen.getByText("not available")).toBeInTheDocument();
    expect(screen.queryByText(/not evidence/)).toBeNull();
  });
  it("labels a rehearsal document as not evidence", () => {
    doc = result("REHEARSAL (development; never evidence)", true);
    render(<ConfirmatoryPanel />);
    expect(screen.getByText(/REHEARSAL \(development; never evidence\): not evidence/)).toBeInTheDocument();
  });
  it("shows an integrity failure instead of a result", () => {
    doc = { status: "INTEGRITY FAILURE", note: "official results fail their integrity hash" };
    render(<ConfirmatoryPanel />);
    expect(screen.getByRole("alert")).toHaveTextContent("INTEGRITY FAILURE");
  });
});
