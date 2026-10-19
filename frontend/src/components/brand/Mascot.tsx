// The HypoSense droplet mascot (inline SVG; decorative only, hidden from assistive technology).
import clsx from "clsx";

export function Mascot({ size = 120, mood = "happy", className }: { size?: number; mood?: "happy" | "curious" | "calm"; className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 200 220" width={size} height={(size * 220) / 200} className={clsx("select-none", className)}>
      <defs>
        <linearGradient id="hs-body" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ece8ff" />
          <stop offset="0.55" stopColor="#c4b5fd" />
          <stop offset="1" stopColor="#8b7cf6" />
        </linearGradient>
        <radialGradient id="hs-shine" cx="0.32" cy="0.3" r="0.35">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.9" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="hs-orb" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#dbeafe" />
          <stop offset="1" stopColor="#93c5fd" />
        </linearGradient>
      </defs>
      <ellipse cx="100" cy="208" rx="58" ry="8" fill="#6d5bd0" opacity="0.12" />
      <path d="M100 8 C 128 52 170 92 170 138 C 170 178 139 204 100 204 C 61 204 30 178 30 138 C 30 92 72 52 100 8 Z" fill="url(#hs-body)" />
      <path d="M100 8 C 128 52 170 92 170 138 C 170 178 139 204 100 204 C 61 204 30 178 30 138 C 30 92 72 52 100 8 Z" fill="url(#hs-shine)" />
      <ellipse cx="74" cy="134" rx="9" ry="12" fill="#1e1b4b" />
      <ellipse cx="126" cy="134" rx="9" ry="12" fill="#1e1b4b" />
      <circle cx="77" cy="129" r="3.2" fill="#fff" />
      <circle cx="129" cy="129" r="3.2" fill="#fff" />
      <ellipse cx="60" cy="152" rx="10" ry="6" fill="#fda4af" opacity="0.55" />
      <ellipse cx="140" cy="152" rx="10" ry="6" fill="#fda4af" opacity="0.55" />
      {mood === "curious" ? (
        <ellipse cx="100" cy="156" rx="7" ry="8" fill="#1e1b4b" />
      ) : mood === "calm" ? (
        <path d="M88 154 Q 100 162 112 154" stroke="#1e1b4b" strokeWidth="4" fill="none" strokeLinecap="round" />
      ) : (
        <path d="M86 150 Q 100 170 114 150 Z" fill="#1e1b4b" />
      )}
      <circle cx="100" cy="186" r="15" fill="url(#hs-orb)" stroke="#fff" strokeWidth="3" />
      <path d="M91 188 L97 182 L102 189 L109 181" stroke="#2563eb" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
