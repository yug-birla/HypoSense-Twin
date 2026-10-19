// The patient most recently opened (per viewer, sessionStorage): lets "Twin anatomy" and
// "Explainability" open that patient. A convenience only; never shared or required.
const KEY = "hyposense.lastPatient";

export const lastPatient = {
  get(): string | null {
    try {
      return typeof window === "undefined" ? null : sessionStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set(k: string): void {
    try {
      sessionStorage.setItem(KEY, k);
    } catch {
      /* storage unavailable */
    }
  },
};
