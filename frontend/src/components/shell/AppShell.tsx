"use client";
import * as RT from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import clsx from "clsx";
import { Activity, FlaskConical, LayoutList, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useState, type ReactNode } from "react";
import { StreamProvider, useStream } from "@/lib/stream";
import { useHealth, useMeta } from "@/lib/queries";

const NAV = [
  { href: "/", label: "Ward board", icon: LayoutList },
  { href: "/patient/", label: "Patient review", icon: UserRound },
  { href: "/evidence/", label: "Evidence", icon: FlaskConical },
];

function Nav() {
  const path = usePathname();
  const params = useSearchParams();
  const key = params.get("key");
  return (
    <nav aria-label="Primary" className="flex flex-col gap-0.5 px-2">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, ""));
        const target = href === "/patient/" && key ? `/patient/?key=${encodeURIComponent(key)}` : href;
        return (
          <Link
            key={href}
            href={target}
            aria-current={active ? "page" : undefined}
            aria-label={label}
            title={label}
            className={clsx(
              "flex h-8 items-center justify-center gap-2.5 rounded-md px-2.5 text-body font-medium transition-colors xl:justify-start",
              active ? "bg-accent-soft text-accent" : "text-ink-2 hover:bg-sunken hover:text-ink",
            )}
          >
            <Icon aria-hidden className="size-4 shrink-0" strokeWidth={2} />
            <span className="hidden xl:inline">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function Connection() {
  const { status } = useStream();
  const health = useHealth();
  const up = health.isSuccess;
  const text = !up ? "Service unreachable" : status === "live" ? "Live" : status === "offline" ? "Stream offline" : "Reconnecting…";
  const tone = !up || status === "offline" ? "bg-low" : status === "live" ? "bg-accent" : "bg-watch";
  return (
    <div className="flex items-center justify-center gap-2 text-small text-ink-3 xl:justify-start" role="status" aria-live="polite" title={text}>
      <span aria-hidden className={clsx("size-2 shrink-0 rounded-full", tone)} />
      <span className="sr-only xl:not-sr-only">{text}</span>
    </div>
  );
}

function ResearchStatus() {
  const meta = useMeta();
  return (
    <>
      <div className="mx-3 hidden rounded-md border border-watch-line bg-watch-tint p-3 xl:block">
        <p className="text-[10.5px] font-bold uppercase tracking-wider text-watch-ink">
          {meta.data?.model_status ?? "DEVELOPMENT"} · Research prototype
        </p>
        <p className="mt-1 text-[11.5px] leading-4 text-watch-ink">
          Not a medical device. Replay of tuning-partition records; evidence is not clinically validated.
        </p>
      </div>
      <p
        className="mx-2 rounded-sm border border-watch-line bg-watch-tint py-1 text-center text-[9.5px] font-bold uppercase leading-3 tracking-wide text-watch-ink xl:hidden"
        title="DEVELOPMENT · Research prototype · Not a medical device"
      >
        Dev
        <br />
        only
      </p>
    </>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <aside className="w-16 shrink-0 border-r border-line bg-surface xl:w-[212px]">
        <div className="sticky top-0 flex h-screen flex-col">
        <div className="flex h-14 items-center justify-center gap-2 px-4 xl:justify-start">
          <span aria-hidden className="flex size-7 items-center justify-center rounded-md bg-ink text-white">
            <Activity className="size-4" strokeWidth={2.5} />
          </span>
          <div className="hidden leading-tight xl:block">
            <p className="text-[13.5px] font-semibold tracking-tight text-ink">HypoSense Twin</p>
            <p className="text-[11px] text-ink-3">Low-glucose early warning</p>
          </div>
        </div>
        <div className="mt-2 flex-1">
          <Suspense>
            <Nav />
          </Suspense>
        </div>
        <div className="flex flex-col gap-3 pb-4">
          <ResearchStatus />
          <div className="px-4">
            <Connection />
          </div>
        </div>
        </div>
      </aside>
      <main id="main" className="min-w-0 flex-1">
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
          <Shell>{children}</Shell>
        </StreamProvider>
      </RT.Provider>
    </QueryClientProvider>
  );
}

export function PageHeader({ title, sub, aside }: { title: ReactNode; sub?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line bg-surface px-6 py-4">
      <div>
        <h1 className="text-display font-semibold tracking-tight text-ink">{title}</h1>
        {sub && <p className="mt-0.5 text-small text-ink-3">{sub}</p>}
      </div>
      {aside}
    </div>
  );
}
