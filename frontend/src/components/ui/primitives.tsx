"use client";
import * as RT from "@radix-ui/react-tooltip";
import clsx from "clsx";
import { AlertTriangle, CircleHelp, Info, RefreshCw, TriangleAlert } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { BADGE_HELP, BADGE_TEXT, stateMeaning, stateStyle, tagHelp, tagText } from "@/lib/states";

/* PRIMARY tier: the policy state. Text + icon + colour; never colour alone. */
export function StatePill({
  state,
  size = "md",
  muted = false,
  explain = false,
}: {
  state: string;
  size?: "sm" | "md" | "lg";
  muted?: boolean; // e.g. a zero count: neutral styling, still readable (no opacity tricks)
  explain?: boolean; // hover/focus shows the plain-language meaning of the state
}) {
  const s = stateStyle(state);
  const Icon = s.icon;
  const pill = (
    <span
      tabIndex={explain ? 0 : undefined}
      aria-description={explain ? stateMeaning(state).text : undefined}
      data-state={state}
      className={clsx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border font-semibold tracking-wide",
        muted ? "border-line bg-surface text-ink-3" : s.pill,
        size === "sm" && "h-6 px-2 text-[10.5px]",
        size === "md" && "h-7 px-2.5 text-[11.5px]",
        size === "lg" && "h-9 px-3.5 text-[13px]",
      )}
    >
      <Icon aria-hidden className={size === "lg" ? "size-4" : "size-3.5"} strokeWidth={2.25} />
      {s.label}
    </span>
  );
  return explain ? <Tip content={stateMeaning(state).text}>{pill}</Tip> : pill;
}

/* Small "?" help affordance with a plain-language explanation (hover or keyboard focus). */
export function Help({ children, label = "What does this mean?" }: { children: ReactNode; label?: string }) {
  return (
    <Tip content={children}>
      <button type="button" aria-label={label} className="inline-flex size-4 items-center justify-center rounded-full align-middle text-ink-4 hover:text-accent focus-visible:text-accent">
        <CircleHelp aria-hidden className="size-3.5" />
      </button>
    </Tip>
  );
}

/* Expandable technical detail (progressive disclosure). */
export function Details({ summary, children }: { summary: ReactNode; children: ReactNode }) {
  return (
    <details className="group rounded-md border border-line bg-sunken px-3 py-2 text-small">
      <summary className="cursor-pointer select-none font-medium text-ink-2 marker:text-ink-4">{summary}</summary>
      <div className="mt-2 text-ink-2">{children}</div>
    </details>
  );
}

/* SECONDARY tier: critical data-quality / processing issues. */
export function QualityBadge({ code }: { code: string }) {
  return (
    <span title={BADGE_HELP[code]} className="inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-sm border border-fault-line bg-fault-tint px-1.5 text-[11px] font-medium text-fault">
      <TriangleAlert aria-hidden className="size-3" strokeWidth={2.25} />
      {BADGE_TEXT[code] ?? code}
    </span>
  );
}

/* TERTIARY tier: informational tags (medication timing unknown, recent input rejected). Quiet by
   design. LOW_CONFIDENCE was removed (P-B12, DEC-2026-10-19-M). */
export function InfoTag({ tag }: { tag: string }) {
  return (
    <span title={tagHelp(tag)} className="inline-block h-5 max-w-full truncate whitespace-nowrap rounded-xs bg-sunken px-1.5 text-[11px] leading-5 text-ink-3">
      {tagText(tag)}
    </span>
  );
}

export function Tip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <RT.Root delayDuration={250}>
      <RT.Trigger asChild>{children}</RT.Trigger>
      <RT.Portal>
        <RT.Content
          sideOffset={6}
          className="z-50 max-w-72 rounded-md border border-line bg-surface px-2.5 py-1.5 text-small text-ink-2 shadow-[0_4px_16px_rgba(16,24,40,0.08)]"
        >
          {content}
        </RT.Content>
      </RT.Portal>
    </RT.Root>
  );
}

export function Panel({
  title,
  aside,
  children,
  className,
  bodyClass,
  id,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
  id?: string;
}) {
  return (
    <section id={id} aria-label={typeof title === "string" ? title : undefined} className={clsx("card", className)}>
      {title !== undefined && (
        <header className="flex min-h-12 items-center justify-between gap-3 px-5 pt-4">
          <h2 className="text-section font-semibold text-ink">{title}</h2>
          {aside}
        </header>
      )}
      <div className={clsx("px-5 pb-5 pt-3", bodyClass)}>{children}</div>
    </section>
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost"; size?: "sm" | "md" }) {
  return (
    <button
      type="button"
      {...rest}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-full font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45",
        size === "md" ? "h-9 px-4 text-body" : "h-8 px-3 text-small",
        variant === "primary" && "bg-accent text-white shadow-[0_4px_12px_rgba(95,79,209,0.28)] hover:bg-[#4f40bd]",
        variant === "secondary" && "border border-line-strong bg-surface text-ink hover:bg-sunken",
        variant === "ghost" && "text-ink-2 hover:bg-sunken",
        className,
      )}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx("animate-pulse rounded-sm bg-sunken", className)} />;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-6 py-10 text-center">
      <Info aria-hidden className="size-5 text-ink-4" />
      <p className="text-body font-medium text-ink-2">{title}</p>
      {children && <div className="max-w-md text-small text-ink-3">{children}</div>}
    </div>
  );
}

export function ErrorBox({ title, detail, onRetry }: { title: string; detail?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-error-line bg-error-tint px-4 py-3 text-error-ink">
      <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div className="flex-1">
        <p className="text-body font-semibold">{title}</p>
        {detail && <p className="text-small">{detail}</p>}
      </div>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          <RefreshCw aria-hidden className="size-3.5" /> Retry
        </Button>
      )}
    </div>
  );
}

export function KV({ k, v, mono }: { k: ReactNode; v: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <dt className="text-small text-ink-3">{k}</dt>
      <dd className={clsx("text-right text-small text-ink tnum", mono && "font-mono text-[11.5px]")}>{v}</dd>
    </div>
  );
}

export function StatusTag({ tone, children }: { tone: "dev" | "ok" | "warn" | "neutral"; children: ReactNode }) {
  return (
    <span
      className={clsx(
        "inline-flex h-5 items-center rounded-xs border px-1.5 text-[10.5px] font-semibold uppercase tracking-wide",
        tone === "dev" && "border-watch-line bg-watch-tint text-watch-ink",
        tone === "ok" && "border-line bg-sunken text-ink-2",
        tone === "warn" && "border-alert-line bg-alert-tint text-alert-ink",
        tone === "neutral" && "border-line bg-surface text-ink-3",
      )}
    >
      {children}
    </span>
  );
}
