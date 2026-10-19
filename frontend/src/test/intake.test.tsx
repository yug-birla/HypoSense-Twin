import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { IntakeFlow } from "@/components/intake/Intake";
import { ObservationPanel, SessionBanner } from "@/components/intake/SessionPanels";
import type { IntakeDraft } from "@/lib/api";
import { bedLabel } from "@/lib/format";
import { patient } from "./fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

// SYNTHETIC draft returned by a mocked server: the page only displays it.
const draft = (status: string, answered: boolean): IntakeDraft => ({
  draft_id: "draft-N0001",
  patient_id: "N0001",
  label: "SYNTHETIC-demo",
  file_name: "SYNTHETIC.csv",
  status,
  findings: [
    { severity: "blocking", code: "REQUIRED_COLUMN_MISSING", message: "No CGM glucose column is mapped.", count: 1 },
    { severity: "info", code: "CONTEXT_ABSENT", message: "No patient context given.", count: 1 },
  ],
  questions: [
    {
      id: "unit:cgm", field: "cgm.unit", prompt: "Which unit are the cgm glucose values in?", reason: "The column header does not state the unit.",
      kind: "choice", options: [["mg/dL", "mg/dL"], ["mmol/L", "mmol/L"]], required: true, suggested: null, answer: answered ? "mg/dL" : null, error: null,
    },
    {
      id: "med:insulin_sc:x", field: "insulin_sc[insulin 10u]", prompt: "“insulin 10u”: which drug and dose was given?", reason: "UNPARSEABLE",
      kind: "text", options: [["keep", "Keep as recorded"]], required: false, suggested: null, answer: null, error: "still not interpretable",
    },
  ],
  mapping: [], preview_headers: [], preview: [], summary: { cgm_readings: 288 }, context: [{ name: "age_y", label: "Age (years)", value: "" }],
  notice: "New data are a separate DEVELOPMENT session.",
});

const upload = vi.fn();
vi.mock("@/lib/api", async (orig) => {
  const m = await orig<typeof import("@/lib/api")>();
  return { ...m, api: { ...m.api, intakeUpload: (...a: unknown[]) => upload(...a) } };
});

function wrap(ui: ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

describe("new-data intake", () => {
  it("labels new-data sessions distinctly from research recordings", () => {
    expect(bedLabel("N0001_0_20300301", "SYNTHETIC-demo")).toBe("SYNTHETIC-demo · N0001");
    expect(bedLabel("N0001_0_20300301")).toBe("New patient N0001");
    expect(bedLabel("2001_0_20201102")).toBe("2001 · R0");
  });
  it("shows server questions; create is disabled until the draft is READY", async () => {
    upload.mockResolvedValueOnce(draft("NEEDS_ANSWERS", false));
    const { container } = wrap(<IntakeFlow />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["a,b\n1,2"], "SYNTHETIC.csv", { type: "text/csv" })] } });
    await waitFor(() => expect(screen.getByText("Which unit are the cgm glucose values in?")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Create patient twin" })).toBeDisabled();
    expect(screen.getByText("required")).toBeInTheDocument();
    expect(screen.getByText("optional")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("still not interpretable");
    expect(screen.getByLabelText("blocking")).toBeInTheDocument();
  });
  it("enables create only for a READY draft", async () => {
    upload.mockResolvedValueOnce(draft("READY", true));
    const { container } = wrap(<IntakeFlow />);
    fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [new File(["x"], "s.csv")] } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Create patient twin" })).toBeEnabled());
  });
  it("a new-data patient view says DEVELOPMENT, not clinically validated, and offers observations", () => {
    const v = patient({ recording_key: "N0001_0_20300301", source: "NEW_DATA_SESSION", label: "SYNTHETIC-demo" });
    wrap(
      <>
        <SessionBanner v={v} />
        <ObservationPanel v={v} offsetS={0} />
      </>,
    );
    expect(screen.getByRole("note")).toHaveTextContent(/DEVELOPMENT model · not clinically validated/);
    for (const t of ["CGM reading", "Capillary glucose", "Meal", "Medication given"]) {
      expect(screen.getByRole("radio", { name: t })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Add to twin" })).toBeDisabled(); // no value yet
  });
});
