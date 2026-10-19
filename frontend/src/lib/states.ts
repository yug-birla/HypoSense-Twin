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
  if (tag.startsWith("MED_TIMING_UNKNOWN:")) return `Timing unknown: ${tag.split(":")[1]}`;
  if (tag === "EVENT_REJECTED") return "Recent input rejected";
  return tag;
}

export const TREND: Record<string, { glyph: string; text: string }> = {
  falling_fast: { glyph: "↓↓", text: "falling rapidly" },
  falling: { glyph: "↓", text: "falling" },
  steady: { glyph: "→", text: "steady" },
  rising: { glyph: "↑", text: "rising" },
  rising_fast: { glyph: "↑↑", text: "rising rapidly" },
};
