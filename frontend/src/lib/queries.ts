"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

// Snapshots are refreshed by stream messages (stream.tsx); the slow interval is only a safety
// net for a silently dropped stream (staleness is still decided by the backend).
const SAFETY_MS = 15_000;

export const useMeta = () => useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: Infinity });
export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 10_000 });
export const useStatus = () => useQuery({ queryKey: ["status"], queryFn: api.status, refetchInterval: SAFETY_MS });
export const useWard = () => useQuery({ queryKey: ["ward"], queryFn: api.ward, refetchInterval: SAFETY_MS });
export const useCases = () => useQuery({ queryKey: ["cases"], queryFn: api.cases, staleTime: Infinity });
export const useEvidence = () => useQuery({ queryKey: ["evidence"], queryFn: api.evidence, staleTime: Infinity });
export const usePatient = (key: string | null) =>
  useQuery({
    queryKey: ["patient", key],
    queryFn: () => api.patient(key!),
    enabled: !!key,
    refetchInterval: SAFETY_MS,
    retry: false,
  });

export function useDataOffset(): number {
  return useMeta().data?.data_utc_offset_s ?? 0;
}
