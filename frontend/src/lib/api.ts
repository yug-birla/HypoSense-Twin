// Typed REST client. Types are generated from the backend OpenAPI schema (ADR-008); this file
// only names them. The browser never computes risk, states or metrics (CLAUDE.md §26).
import type { components } from "./openapi";

type Schemas = components["schemas"];
export type Ward = Schemas["Ward"];
export type Bed = Schemas["Bed"];
export type DecisionView = Schemas["DecisionView"];
export type PatientView = Schemas["PatientView"];
export type TimelinePoint = Schemas["TimelinePoint"];
export type LedgerEntry = Schemas["LedgerEntry"];
export type FactorGroup = Schemas["FactorGroup"];
export type Trend = Schemas["Trend"];
export type Case = Schemas["Case"];
export type ReplayStatus = Schemas["ReplayStatus"];
export type Meta = Schemas["Meta"];
export type Evidence = Schemas["Evidence"];
export type LadderModel = Schemas["LadderModel"];
export type AckRequest = Schemas["AckRequest"];
export type AckRecord = Schemas["AckRecord"];
export type Health = Schemas["Health"];

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly kind: string,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "unreachable", "The HypoSense service is not reachable.");
  }
  if (!res.ok) {
    let kind = "error";
    let detail = `Request failed (${res.status}).`;
    try {
      const j = (await res.json()) as { error?: string; detail?: unknown };
      kind = j.error ?? kind;
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, kind, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),
  meta: () => request<Meta>("GET", "/api/meta"),
  evidence: () => request<Evidence>("GET", "/api/evidence"),
  cases: () => request<Case[]>("GET", "/api/replay/cases"),
  status: () => request<ReplayStatus>("GET", "/api/replay/status"),
  ward: () => request<Ward>("GET", "/api/ward"),
  patient: (key: string) => request<PatientView>("GET", `/api/patients/${encodeURIComponent(key)}`),
  select: (keys: string[]) => request<ReplayStatus>("POST", "/api/replay/select", { recording_keys: keys }),
  play: () => request<ReplayStatus>("POST", "/api/replay/play"),
  pause: () => request<ReplayStatus>("POST", "/api/replay/pause"),
  reset: () => request<ReplayStatus>("POST", "/api/replay/reset"),
  speed: (speed: number) => request<ReplayStatus>("POST", "/api/replay/speed", { speed }),
  step: (n: number) => request<ReplayStatus>("POST", "/api/replay/step", { n }),
  advance: (seconds: number) => request<ReplayStatus>("POST", "/api/replay/advance", { seconds }),
  seek: (offset_s: number) => request<ReplayStatus>("POST", "/api/replay/seek", { offset_s }),
  acknowledge: (req: AckRequest) => request<AckRecord>("POST", "/api/acknowledgements", req),
};
