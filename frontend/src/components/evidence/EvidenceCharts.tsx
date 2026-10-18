"use client";
import { useMemo } from "react";
import type { Evidence } from "@/lib/api";
import { AXIS, Chart, TOOLTIP, type ChartOption } from "@/components/ui/Chart";

export const MODEL_ORDER = ["M0", "M1", "M2", "M3r", "M3"] as const;
export const MODEL_COLOR: Record<string, string> = {
  M0: "#9aa3b2",
  M1: "#7c8ca3",
  M2: "#3f6fa8",
  M3r: "#8b5cc7",
  M3: "#0e6e6a",
};
export const MODEL_DESC: Record<string, string> = {
  M0: "Trend projection (no learning)",
  M1: "CGM features",
  M2: "CGM + context + meals",
  M3r: "M2 + raw medication timing",
  M3: "M2 + medication exposure",
};

export function FrocChart({ ev, pop }: { ev: Evidence; pop: "treated" | "all" }) {
  const option = useMemo<ChartOption>(() => {
    const curves = ev.curves?.[pop] ?? {};
    return {
      grid: { left: 52, right: 28, top: 44, bottom: 40 },
      legend: { top: 0, left: 46, itemWidth: 16, itemHeight: 3, textStyle: { color: "#3f4857", fontSize: 11 } },
      xAxis: { type: "value", min: 0, max: 3, name: "False alerts per patient-day", nameLocation: "middle", nameGap: 26, ...AXIS },
      yAxis: { type: "value", min: 0, max: 1, name: "Episode sensitivity", nameLocation: "middle", nameGap: 38, ...AXIS, axisLabel: { ...AXIS.axisLabel, formatter: (v: number) => `${Math.round(v * 100)}%` } },
      tooltip: { ...TOOLTIP, trigger: "axis", valueFormatter: (v: number) => `${(v * 100).toFixed(1)}%` },
      series: MODEL_ORDER.filter((m) => curves[m]).map((m) => ({
        name: m,
        type: "line",
        step: "end",
        showSymbol: false,
        data: curves[m]!.fa_per_day.map((f, i) => [f, curves[m]!.sensitivity[i]]),
        lineStyle: { width: m === "M3" || m === "M2" ? 2 : 1.25, color: MODEL_COLOR[m] },
        itemStyle: { color: MODEL_COLOR[m] },
        markLine:
          m === "M3"
            ? {
                silent: true,
                symbol: "none",
                lineStyle: { color: "#c2410c", type: "dashed", width: 1 },
                label: { formatter: "budget 1 FA/day", fontSize: 10, color: "#9a3412", position: "end", rotate: 0 },
                data: [{ xAxis: 1 }],
              }
            : undefined,
      })),
    };
  }, [ev, pop]);
  return <Chart option={option} height={300} label={`Operating curves (${pop} patients): sensitivity versus false alerts per day`} />;
}

export function ReliabilityChart({ ev, pop, model }: { ev: Evidence; pop: "treated" | "all"; model: string }) {
  const bins = ev.ladder[pop]?.models[model]?.reliability ?? [];
  const option = useMemo<ChartOption>(() => {
    const max = Math.max(0.05, ...bins.map((b) => Math.max(b.mean_p, b.mean_y))) * 1.1;
    return {
      grid: { left: 52, right: 16, top: 12, bottom: 40 },
      xAxis: { type: "value", min: 0, max, name: "Mean predicted probability", nameLocation: "middle", nameGap: 26, ...AXIS, axisLabel: { ...AXIS.axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
      yAxis: { type: "value", min: 0, max, name: "Observed rate", nameLocation: "middle", nameGap: 38, ...AXIS, axisLabel: { ...AXIS.axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
      tooltip: { ...TOOLTIP, trigger: "item", formatter: (p: { value: [number, number, number] }) => `predicted ${(p.value[0] * 100).toFixed(2)}% · observed ${(p.value[1] * 100).toFixed(2)}% · n ${p.value[2]}` },
      series: [
        { type: "line", data: [[0, 0], [max, max]], showSymbol: false, silent: true, lineStyle: { color: "#cbd1d9", type: "dashed", width: 1 } },
        {
          type: "line",
          data: bins.map((b) => [b.mean_p, b.mean_y, b.n]),
          symbolSize: 6,
          lineStyle: { color: MODEL_COLOR[model] ?? "#0e6e6a", width: 1.5 },
          itemStyle: { color: MODEL_COLOR[model] ?? "#0e6e6a" },
        },
      ],
    };
  }, [bins, model]);
  if (!bins.length) return <p className="py-8 text-center text-small text-ink-3">No calibration data for {model}.</p>;
  return <Chart option={option} height={240} label={`Reliability diagram for ${model}`} />;
}

/** Point + 95 % interval on a shared scale (inline SVG; no computation beyond scaling). */
export function IntervalBar({
  point,
  ci,
  lo,
  hi,
  zero,
  color = "#0e6e6a",
}: {
  point: number | null | undefined;
  ci: number[] | null | undefined;
  lo: number;
  hi: number;
  zero?: boolean;
  color?: string;
}) {
  const W = 160;
  const x = (v: number) => ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * W;
  return (
    <svg width={W} height={16} aria-hidden className="overflow-visible">
      <line x1={0} x2={W} y1={8} y2={8} stroke="#eceff3" strokeWidth={4} strokeLinecap="round" />
      {zero && <line x1={x(0)} x2={x(0)} y1={1} y2={15} stroke="#8d96a5" strokeWidth={1} />}
      {ci && ci.length === 2 && <line x1={x(ci[0]!)} x2={x(ci[1]!)} y1={8} y2={8} stroke={color} strokeOpacity={0.7} strokeWidth={4} strokeLinecap="round" />}
      {point !== null && point !== undefined && <circle cx={x(point)} cy={8} r={4} fill={color} stroke="#fff" strokeWidth={1.5} />}
    </svg>
  );
}
