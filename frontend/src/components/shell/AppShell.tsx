"use client";
import * as RT from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import clsx from "clsx";
import {
  FlaskConical,
  Home,
  LayoutList,
  Lightbulb,
  Network,
  PlayCircle,
  Search,
  ShieldCheck,
  UserPlus,
  UserRound,
  Clapperboard,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { StreamProvider, useStream } from "@/lib/stream";
import { DemoProvider, useDemo } from "@/lib/demo";
import { bedLabel } from "@/lib/format";
import { lastPatient } from "@/lib/lastPatient";
import { DemoDock } from "@/components/demo/DemoDock";
import { Mascot } from "@/components/brand/Mascot";
import { useConnectionLost, useHealth, useMeta, useWard } from "@/lib/queries";

type Item = { href: string; label: string; icon: typeof Home; patient?: "twin" | "explain" };
const NAV: Item[][] = [
  [
    { href: "/", label: "Welcome", icon: Home },
    { href: "/ward/", label: "Ward board", icon: LayoutList },
    { href: "/patient/", label: "Patient review", icon: UserRound },
    { href: "/replay/", label: "Replay studio", icon: Clapperboard },
    { href: "/patient/", label: "Twin anatomy", icon: Network, patient: "twin" },
    { href: "/patient/", label: "Explainability", icon: Lightbulb, patient: "explain" },
    { href: "/evidence/", label: "Evidence garden", icon: FlaskConical },
  ],
  [
    { href: "/intake/", label: "Add patient", icon: UserPlus },
    { href: "/demo/", label: "Guided demo", icon: PlayCircle },
  ],
];

function Nav() {
  const path = usePathname();
  const params = useSearchParams();
  const key = params.get("key") ?? lastPatient.get();
  const tab = params.get("tab");
  return (
    <nav aria-label="Primary" className="flex flex-col gap-3 px-3">
      {NAV.map((group, gi) => (
        <div key={gi} className={clsx("flex flex-col gap-1", gi > 0 && "border-t border-line pt-3")}>
          {group.map(({ href, label, icon: Icon, patient }) => {
            const onPatient = path.startsWith("/patient");
            const active = patient
              ? onPatient && tab === patient
              : href === "/patient/"
                ? onPatient && tab !== "twin" && tab !== "explain"
                : href === "/"
                  ? path === "/"
                  : path.startsWith(href.replace(/\/$/, ""));
            const q = new URLSearchParams();
            if (href === "/patient/" && key) q.set("key", key);
            if (patient) q.set("tab", patient);
            const target = q.size ? `${href}?${q.toString()}` : href;
            return (
              <Link
                key={label}
                href={target}
                aria-current={active ? "page" : undefined}
                aria-label={label}
                title={label}
                className={clsx(
                  "flex h-10 items-center justify-center gap-3 rounded-xl px-3 text-[14px] font-medium transition-colors xl:justify-start",
                  active ? "bg-accent-soft text-accent shadow-[inset_3px_0_0_var(--color-accent)]" : "text-ink-2 hover:bg-sunken hover:text-ink",
                )}
              >
                <Icon aria-hidden className="size-[18px] shrink-0" strokeWidth={2} />
                <span className="hidden xl:inline">{label}</span>
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function Connection() {
  const { status } = useStream();
  const health = useHealth();
  const up = health.isSuccess;
  const text = !up ? "Service unreachable" : status === "live" ? "Live" : status === "offline" ? "Stream offline" : "Reconnecting…";
  const tone = !up || status === "offline" ? "bg-low" : status === "live" ? "bg-[#22a06b]" : "bg-watch";
  return (
    <div className="flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-small text-ink-2" role="status" aria-live="polite" title={text}>
      <span aria-hidden className={clsx("size-2 shrink-0 rounded-full", tone)} />
      <span>{text}</span>
    </div>
  );
}

function LostBanner() {
  const lost = useConnectionLost();
  if (!lost) return null;
  return (
    <div role="alert" className="sticky top-0 z-30 mx-6 mt-3 rounded-xl border border-low-line bg-low-tint px-5 py-2 text-body font-semibold text-low-ink">
      Connection to the HypoSense service lost. Values on screen are NOT current; patient states are hidden until it reconnects.
    </div>
  );
}

/** Jump to a patient that is on the board now (replay bed or new-data session). Nothing else is searched. */
function PatientSearch() {
  const ward = useWard();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const hits = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    return (ward.data?.beds ?? []).filter((b) => `${b.recording_key} ${bedLabel(b.recording_key, b.label)}`.toLowerCase().includes(t)).slice(0, 6);
  }, [q, ward.data]);
  const go = (k: string) => {
    setQ("");
    setOpen(false);
    router.push(`/patient/?key=${encodeURIComponent(k)}`);
  };
  return (
    <div className="relative w-full max-w-[460px]">
      <Search aria-hidden className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-4" />
      <input
        ref={ref}
        role="combobox"
        aria-expanded={open && hits.length > 0}
        aria-controls="patient-search-results"
        aria-label="Find a patient on the board"
        placeholder="Find a patient on the board…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => e.key === "Enter" && hits[0] && go(hits[0].recording_key)}
        className="h-11 w-full rounded-full border border-line bg-surface pl-10 pr-16 text-body text-ink shadow-[0_1px_2px_rgba(30,27,75,0.04)] placeholder:text-ink-4"
      />
      <kbd className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded-md border border-line bg-sunken px-1.5 text-[11px] text-ink-3">Ctrl K</kbd>
      {open && q.trim() && (
        <ul id="patient-search-results" role="listbox" className="card absolute left-0 right-0 top-12 z-40 p-1.5">
          {hits.length === 0 ? (
            <li className="px-3 py-2 text-small text-ink-3">No patient on the board matches. Start a replay or add a patient first.</li>
          ) : (
            hits.map((b) => (
              <li key={b.recording_key} role="option" aria-selected={false}>
                <button type="button" onMouseDown={() => go(b.recording_key)} className="w-full rounded-lg px-3 py-2 text-left text-body hover:bg-sunken">
                  {bedLabel(b.recording_key, b.label)} <span className="text-small text-ink-4">· {b.decision.state.replace("_", " ")}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

function TopBar() {
  const meta = useMeta();
  return (
    <header className="flex flex-wrap items-center gap-3 px-6 pt-5">
      <PatientSearch />
      <div className="ml-auto flex flex-wrap items-center gap-2.5">
        <div className="flex items-center gap-2 rounded-2xl border border-line bg-surface px-3.5 py-1.5" title="Not a medical device">
          <ShieldCheck aria-hidden className="size-4 text-accent" />
          <span className="leading-tight">
            <span className="block text-small font-semibold text-ink">Research mode</span>
            <span className="block text-[11px] text-ink-3">
              Retrospective replay (ShanghaiT2DM) · {meta.data?.model_status ?? "DEVELOPMENT"} model
            </span>
          </span>
        </div>
        <Connection />
      </div>
    </header>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const demo = useDemo();
  return (
    <div className="flex min-h-screen">
      <aside className="w-[72px] shrink-0 border-r border-line bg-surface/80 backdrop-blur xl:w-[236px]">
        <div className="sticky top-0 flex h-screen flex-col">
          <Link href="/" className="flex h-20 items-center justify-center gap-2.5 px-4 xl:justify-start xl:px-5">
            <span aria-hidden className="flex size-10 items-center justify-center rounded-2xl bg-accent-soft">
              <Mascot size={30} />
            </span>
            <span className="hidden leading-tight xl:block">
              <span className="block text-[19px] font-bold tracking-tight text-accent">HypoSense</span>
              <span className="block text-[13px] font-medium text-ink-2">Twin</span>
            </span>
          </Link>
          <div className="mt-2 flex-1 overflow-y-auto">
            <Suspense>
              <Nav />
            </Suspense>
          </div>
          <div className="hidden flex-col gap-3 px-4 pb-4 xl:flex">
            <div className="relative flex items-end gap-1">
              <Mascot size={64} mood="calm" className="shrink-0" />
              <p className="mb-6 rounded-2xl rounded-bl-sm border border-line bg-surface px-3 py-2 text-[12px] leading-4 text-ink-2 shadow-sm">
                Every number here is development evidence until the sealed test.
              </p>
            </div>
            <div className="rounded-2xl border border-line bg-accent-soft/60 px-3.5 py-3">
              <p className="text-[12px] font-semibold text-ink">Research prototype</p>
              <p className="text-[11px] leading-4 text-ink-3">Not a medical device. Never suggests doses or treatment.</p>
            </div>
          </div>
        </div>
      </aside>
      <main id="main" className={clsx("min-w-0 flex-1", demo.active && "pb-[340px]")}>
        <TopBar />
        <LostBanner />
        {children}
      </main>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [qc] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
      }),
  );
  return (
    <QueryClientProvider client={qc}>
      <RT.Provider>
        <StreamProvider>
          <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2">
            Skip to content
          </a>
          <Suspense>
            <DemoProvider>
              <Shell>{children}</Shell>
              <DemoDock />
            </DemoProvider>
          </Suspense>
        </StreamProvider>
      </RT.Provider>
    </QueryClientProvider>
  );
}

/** Page hero: gradient banner with the title, a short explanation and the mascot's speech bubble. */
export function PageHeader({
  title,
  sub,
  aside,
  bubble,
  mood = "happy",
}: {
  title: ReactNode;
  sub?: ReactNode;
  aside?: ReactNode;
  bubble?: ReactNode;
  mood?: "happy" | "curious" | "calm";
}) {
  return (
    <div className="px-6 pt-5">
      <div className="hero-grad card relative flex min-h-[132px] flex-wrap items-center justify-between gap-4 overflow-hidden px-7 py-5">
        <div className="relative z-10 max-w-[720px]">
          <h1 className="text-[30px] font-bold leading-tight tracking-tight text-ink">{title}</h1>
          {sub && <p className="mt-1.5 text-[15px] leading-snug text-ink-2">{sub}</p>}
          {aside && <div className="mt-3">{aside}</div>}
        </div>
        <div className="relative z-10 hidden items-end gap-2 lg:flex">
          {bubble && (
            <p className="mb-10 max-w-[230px] rounded-2xl rounded-br-sm border border-line bg-surface/95 px-3.5 py-2.5 text-[13px] leading-snug text-ink-2 shadow-sm">
              {bubble}
            </p>
          )}
          <Mascot size={92} mood={mood} />
        </div>
        <span aria-hidden className="pointer-events-none absolute -right-10 -top-16 size-64 rounded-full bg-[#e3dcff] opacity-60 blur-2xl" />
        <span aria-hidden className="pointer-events-none absolute -bottom-20 right-40 size-56 rounded-full bg-[#dff1ff] opacity-70 blur-2xl" />
      </div>
    </div>
  );
}
