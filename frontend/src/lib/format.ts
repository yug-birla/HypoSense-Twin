// Formatting only: no clinical logic. Times are shown on the DATA clock (the recording's local
// time, offset from /api/meta), because replayed records keep their original timestamps.

export function clock(ts: number, offsetS: number): string {
  const d = new Date((ts + offsetS) * 1000);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export function dateClock(ts: number, offsetS: number): string {
  const d = new Date((ts + offsetS) * 1000);
  const mon = d.toLocaleString("en-GB", { month: "short", timeZone: "UTC" });
  return `${d.getUTCDate()} ${mon} ${clock(ts, offsetS)}`;
}

export function age(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return "now";
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  return `${h} h ${m % 60} min ago`;
}

export function duration(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return d > 0 ? `${d} d ${h} h` : h > 0 ? `${h} h ${m} min` : `${m} min`;
}

/** Pseudonymous display id from the dataset recording key ("2001_0_20201102" -> "2001 · R0"). */
export function bedLabel(recordingKey: string, label?: string | null): string {
  const [p, r] = recordingKey.split("_");
  if (recordingKey.startsWith("N")) return label ? `${label} · ${p}` : `New patient ${p}`;
  return `${p ?? recordingKey} · R${r ?? "?"}`;
}

export function mgdl(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${Math.round(v)}`;
}

export function rate(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  const s = v > 0 ? "+" : v < 0 ? "−" : "±";
  return `${s}${Math.abs(v).toFixed(1)}`;
}

export function pct(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;
}

export function num(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined ? "—" : v.toFixed(digits);
}

export function shortHash(h: string | null | undefined, n = 10): string {
  return h ? h.slice(0, n) : "—";
}
