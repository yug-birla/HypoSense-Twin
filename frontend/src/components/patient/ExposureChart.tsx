"use client";
import { useMemo } from "react";
import type { PatientView } from "@/lib/api";
import { clock } from "@/lib/format";
import { AXIS, Chart, TOOLTIP, type ChartOption } from "@/components/ui/Chart";

/** Estimated medication exposure (backend S3 engine values per reading) vs recorded doses. */
export function ExposureChart({ view, offsetS }: { view: PatientView; offsetS: number }) {
  const pts = view.timeline;
  const has = (k: string) => pts.some((p) => (p.exposure[k] ?? 0) > 0);
  const anyInsulin = has("act_insulin_total") || has("iob_insulin");
  const anySu = has("act_su") || has("act_glinide");
  const option = useMemo<ChartOption>(() => {
    const ms = (ts: number) => (ts + offsetS) * 1000;
    const t0 = ms(Math.max(view.now_ts - 24 * 3600, pts[0]?.ts ?? view.now_ts - 24 * 3600));
    const t1 = ms(view.now_ts);
    const line = (k: string, name: string, color: string, axis: number, dashed = false, area = false) => ({
      name,
      type: "line",
      yAxisIndex: axis,
      data: pts.map((p) => [ms(p.ts), p.exposure[k] ?? null]),
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 1.5, color, type: dashed ? "dashed" : "solid" },
      itemStyle: { color },
      areaStyle: area ? { color, opacity: 0.12 } : undefined,
    });
    const series: object[] = [];
    if (anyInsulin) {
      series.push(line("act_insulin_total", "Estimated insulin activity (IU/h)", "#2f6fd6", 0, false, true));
      series.push(line("iob_insulin", "Estimated insulin on board (IU)", "#93b4ea", 1, true));
    }
    if (anySu) {
      series.push(line("act_su", "Estimated sulfonylurea activity (relative)", "#8b5cc7", anyInsulin ? 1 : 0));
    }
    series.push({
      name: "Recorded dose",
      type: "scatter",
      yAxisIndex: 0,
      data: view.doses.map((d) => ({ value: [ms(d.ts), 0], dose: d })),
      symbol: "rect",
      symbolSize: [2, 10],
      itemStyle: { color: "#3f4857" },
      z: 4,
    });
    return {
      grid: { left: 52, right: 40, top: 34, bottom: 26 },
      legend: { top: 0, right: 8, itemWidth: 14, itemHeight: 8, textStyle: { color: "#3f4857", fontSize: 11 } },
      xAxis: { type: "time", min: t0, max: t1, ...AXIS, splitLine: { show: false }, axisLabel: { ...AXIS.axisLabel, formatter: (v: number) => clock(v / 1000 - offsetS, offsetS) } },
      yAxis: [
        { type: "value", min: 0, ...AXIS, splitNumber: 3 },
        { type: "value", min: 0, ...AXIS, splitNumber: 3, splitLine: { show: false } },
      ],
      series,
      tooltip: { ...TOOLTIP, trigger: "axis", valueFormatter: (v: number | null) => (v === null ? "—" : Number(v).toFixed(2)) },
    };
  }, [view, offsetS, pts, anyInsulin, anySu]);

  if (!anyInsulin && !anySu && view.doses.length === 0) {
    return <p className="py-6 text-center text-small text-ink-3">No logged glucose-lowering medication in the last 24 h.</p>;
  }
  return <Chart option={option} height={190} label="Estimated medication exposure over the last 24 hours, with recorded doses" />;
}
