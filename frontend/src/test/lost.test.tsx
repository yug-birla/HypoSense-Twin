// F1 regression (S8 review): when the service or stream is lost, ward states must NOT stay on
// screen as if current. SYNTHETIC fixture data.
import * as RT from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import WardPage from "@/app/page";
import { bed } from "./fixtures";

const state = { lost: false };
const ward = { data: { session_id: "s", offset_s: 0, beds: [bed({ decision: { ...bed().decision, state: "ALERT", p: 0.3, p_text: "30%" } })] }, isError: false };
const status = { data: { session_id: "s", recordings: ["9001_0_20200101"], playing: false, speed: 120, offset_s: 0, duration_s: 100, finished: false, decisions_logged: 1, source: "" }, isError: false, isSuccess: true };

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/queries", () => ({
  useWard: () => ward,
  useStatus: () => status,
  useDataOffset: () => 0,
  useConnectionLost: () => state.lost,
  useCases: () => ({ data: [] }),
}));

function page() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <RT.Provider>
        <WardPage />
      </RT.Provider>
    </QueryClientProvider>,
  );
}

it("shows bed states while connected", () => {
  state.lost = false;
  page();
  expect(screen.getAllByText("ALERT").length).toBeGreaterThan(0);
  expect(screen.getByText("30%")).toBeInTheDocument();
});

it("hides bed states and risk when the connection is lost", () => {
  state.lost = true;
  page();
  expect(screen.getByText("Ward state not current")).toBeInTheDocument();
  expect(screen.queryByText("30%")).toBeNull();
  expect(screen.queryByRole("table")).toBeNull();
  expect(screen.getByRole("button", { name: "Play replay" })).toBeDisabled();
});
