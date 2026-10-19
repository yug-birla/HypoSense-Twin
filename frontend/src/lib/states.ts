// Visual mapping of BACKEND policy states (policy/decide.py PolicyState). Presentation only:
// the browser never decides a state. Every state has text + icon + colour (never colour alone).
import {
  ArrowDownToLine,
  BellRing,
  Eye,
  Minus,
  CircleDashed,
  OctagonX,
  type LucideIcon,
} from "lucide-react";

export type PolicyState =
  | "SYSTEM_ERROR"
  | "LOW_NOW"
  | "ALERT"
  | "WATCH"
  | "INSUFFICIENT_DATA"
  | "NO_ALERT";

export interface StateStyle {
  label: string;
  icon: LucideIcon;
  /** pill classes: strongest states are solid, others tinted */
  pill: string;
  /** row accent bar colour */
  bar: string;
  /** text colour for inline use */
  ink: string;
  attention: boolean;
}

export const STATE: Record<PolicyState, StateStyle> = {
  LOW_NOW: {
    label: "LOW NOW",
    icon: ArrowDownToLine,
    pill: "bg-low text-white border-low",
    bar: "bg-low",
    ink: "text-low-ink",
    attention: true,
  },
  ALERT: {
    label: "ALERT",
    icon: BellRing,
    pill: "bg-alert-tint text-alert-ink border-alert-line",
    bar: "bg-alert",
    ink: "text-alert-ink",
    attention: true,
  },
  WATCH: {
    label: "WATCH",
    icon: Eye,
    pill: "bg-watch-tint text-watch-ink border-watch-line",
    bar: "bg-watch",
    ink: "text-watch-ink",
    attention: true,
  },
  SYSTEM_ERROR: {
    label: "SYSTEM ERROR",
    icon: OctagonX,
    pill: "bg-error-tint text-error-ink border-error-line",
    bar: "bg-error",
    ink: "text-error-ink",
    attention: true,
  },
  INSUFFICIENT_DATA: {
    label: "INSUFFICIENT DATA",
    icon: CircleDashed,
    pill: "bg-nodata-tint text-nodata-ink border-nodata-line border-dashed",
    bar: "bg-nodata-line",
    ink: "text-nodata-ink",
    attention: false,
  },
  NO_ALERT: {
    label: "NO ALERT",
    icon: Minus,
    pill: "bg-calm-tint text-calm-ink border-calm-line",
    bar: "bg-transparent",
    ink: "text-calm-ink",
    attention: false,
  },
};

export function stateStyle(s: string): StateStyle {
  return STATE[(s in STATE ? s : "SYSTEM_ERROR") as PolicyState];
}

/** Critical quality badges (secondary tier) vs informational tags (tertiary tier). The backend
 *  already separates them (`badges` vs `info_tags`); these are display names only. */
export const BADGE_TEXT: Record<string, string> = {
  SENSOR_FAULT_SUSPECTED: "Sensor fault suspected",
  RUNNER_HALTED: "Processing halted",
  INPUT_REJECTED: "Input rejected",
};

export function tagText(tag: string): string {
  if (tag.startsWith("MED_TIMING_UNKNOWN:")) return `${MED_CLASS[tag.split(":")[1] ?? ""] ?? tag.split(":")[1]} dose times not recorded`;
  if (tag === "EVENT_REJECTED") return "Recent input rejected";
  return tag;
}

const MED_CLASS: Record<string, string> = { insulin: "Insulin", sulfonylurea: "Sulfonylurea", glinide: "Glinide" };

/** Plain-language meaning of each BACKEND policy state (policy/decide.py, Table 14.1). These
 *  explain the state; they never decide it and never advise treatment. */
export const STATE_MEANING: Record<PolicyState, { kind: "observed" | "predicted" | "unavailable"; text: string }> = {
  LOW_NOW: {
    kind: "observed",
    text: "Observed now: the latest CGM reading is below 70 mg/dL, or the patient is in (or less than 60 min after) a CGM-detected low episode.",
  },
  ALERT: {
    kind: "predicted",
    text: "Prediction: the estimated risk of a new CGM-detected low within 60 min has reached the alert threshold. Glucose is not necessarily low now.",
  },
  WATCH: {
    kind: "predicted",
    text: "Prediction: the estimated risk is elevated (at or above the watch threshold) but below the alert threshold.",
  },
  NO_ALERT: {
    kind: "predicted",
    text: "Prediction: the estimated risk is below the watch threshold. This is not a guarantee that no low will occur.",
  },
  INSUFFICIENT_DATA: {
    kind: "unavailable",
    text: "No forecast: there is not enough valid recent CGM data (no reading for > 20 min, too few readings in the last 2 h, sensor warm-up or a rapid change).",
  },
  SYSTEM_ERROR: {
    kind: "unavailable",
    text: "No forecast: the system could not process the latest data reliably. No earlier prediction is shown as current.",
  },
};

export function stateMeaning(s: string) {
  return STATE_MEANING[(s in STATE_MEANING ? s : "SYSTEM_ERROR") as PolicyState];
}

export const BADGE_HELP: Record<string, string> = {
  SENSOR_FAULT_SUSPECTED: "Some recent CGM readings look physiologically implausible; interpret them with care and confirm with a capillary measurement per local protocol.",
  RUNNER_HALTED: "Processing stopped after repeated input errors; no current state is shown.",
  INPUT_REJECTED: "A recent non-glucose entry (meal or medication) could not be used; medication information may be incomplete.",
};

export function tagHelp(tag: string): string {
  if (tag.startsWith("MED_TIMING_UNKNOWN:"))
    return "This medicine is prescribed for the patient, but no timed administration is recorded, so its activity cannot be estimated.";
  if (tag === "EVENT_REJECTED") return BADGE_HELP.INPUT_REJECTED!;
  return tag;
}

export const TREND: Record<string, { glyph: string; text: string }> = {
  falling_fast: { glyph: "↓↓", text: "falling rapidly" },
  falling: { glyph: "↓", text: "falling" },
  steady: { glyph: "→", text: "steady" },
  rising: { glyph: "↑", text: "rising" },
  rising_fast: { glyph: "↑↑", text: "rising rapidly" },
};
