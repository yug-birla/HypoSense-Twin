"use client";
// SSE client for /api/stream (ADR-008, stream v1). Messages only TRIGGER refetches of the
// canonical snapshot endpoints; the browser never assembles a patient state from deltas.
import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { API_BASE } from "./api";

export type StreamStatus = "connecting" | "live" | "reconnecting" | "offline";
export const STREAM_VERSION = 1;
const REFRESH_MS = 400; // coalesce bursts (a replay tick can emit many decisions)
const RETRY_MS = [1000, 2000, 5000, 10000];

export interface StreamMessage {
  v: number;
  type: string;
  [k: string]: unknown;
}

interface StreamCtx {
  status: StreamStatus;
  lastMessageAt: number | null;
  lastNotification: StreamMessage | null;
}

const Ctx = createContext<StreamCtx>({ status: "connecting", lastMessageAt: null, lastNotification: null });

/** Which cached queries a message invalidates. Pure; unit-tested. */
export function queriesFor(msg: StreamMessage): string[][] {
  switch (msg.type) {
    case "session":
      return [["status"], ["ward"], ["patient"]];
    case "tick":
      return [["status"]];
    case "bed_state":
    case "decision":
    case "notification":
    case "error":
      return [["ward"], ["patient"]];
    case "acknowledgement":
      return [["ward"], ["patient"]];
    default:
      return [];
  }
}

export function parseMessage(data: string): StreamMessage | null {
  try {
    const m = JSON.parse(data) as StreamMessage;
    if (typeof m !== "object" || m === null || m.v !== STREAM_VERSION || typeof m.type !== "string") {
      return null; // unknown version: ignore rather than misinterpret
    }
    return m;
  } catch {
    return null;
  }
}

export function StreamProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [lastMessageAt, setLast] = useState<number | null>(null);
  const [lastNotification, setNotif] = useState<StreamMessage | null>(null);
  const pending = useRef<Set<string>>(new Set());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let es: EventSource | null = null;
    let attempt = 0;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const flush = () => {
      timer.current = null;
      for (const k of pending.current) qc.invalidateQueries({ queryKey: [k] });
      pending.current.clear();
    };
    const onMessage = (ev: MessageEvent<string>) => {
      const m = parseMessage(ev.data);
      if (!m) return;
      setLast(Date.now());
      if (m.type === "notification") setNotif(m);
      for (const q of queriesFor(m)) pending.current.add(q[0]!);
      if (!timer.current) timer.current = setTimeout(flush, REFRESH_MS);
    };
    const connect = () => {
      if (closed) return;
      es = new EventSource(`${API_BASE}/api/stream`);
      es.onopen = () => {
        attempt = 0;
        setStatus("live");
        for (const k of ["status", "ward", "patient", "health"]) qc.invalidateQueries({ queryKey: [k] }); // resync live views
      };
      for (const t of ["session", "tick", "decision", "notification", "error", "bed_state", "acknowledgement"]) {
        es.addEventListener(t, onMessage as EventListener);
      }
      es.onerror = () => {
        es?.close();
        es = null;
        if (closed) return;
        setStatus(attempt >= RETRY_MS.length ? "offline" : "reconnecting");
        const wait = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)]!;
        attempt += 1;
        retry = setTimeout(connect, wait);
      };
    };
    connect();
    return () => {
      closed = true;
      es?.close();
      if (retry) clearTimeout(retry);
      if (timer.current) clearTimeout(timer.current);
    };
  }, [qc]);

  return <Ctx.Provider value={{ status, lastMessageAt, lastNotification }}>{children}</Ctx.Provider>;
}

export const useStream = () => useContext(Ctx);
