"use client";
import clsx from "clsx";
import { useMemo, useState } from "react";
import type { PatientView, TimelinePoint } from "@/lib/api";
import { clock } from "@/lib/format";
import { AXIS, Chart, TOOLTIP, type ChartOption } from "@/components/ui/Chart";

const GAP_S = 1200; // a reading gap > 20 min is drawn as a gap (never interpolated)

/** Contiguous runs of a backend flag -> [start, end] (display only). */
export function runs(points: TimelinePoint[], flag: (p: TimelinePoint) => boolean): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  let start: number | null = null;
  let last = 0;
  for (const p of points) {
    if (flag(p)) {
      if (start === null) start = p.ts;
      last = p.ts;
    } else if (start !== null) {
      out.push([start, last]);
      start = null;
    }
  }
  if (start !== null) out.push([start, last]);
  return out;
}

/** CGM series with explicit nulls at gaps > 20 min (so the line breaks honestly). */
export function withGaps(points: TimelinePoint[]): Array<[number, number | null]> {
  const out: Array<[number, number | null]> = [];
  let prev: number | null = null;
  for (const p of points) {
    if (prev !== null && p.ts - prev > GAP_S) out.push([prev + 1, null]);
    out.push([p.ts, p.cgm_mgdl]);
    prev = p.ts;
  }
  return out;
}

type Layer = "episodes" | "notifications" | "fault" | "risk" | "events";
const LAYERS: Array<[Layer, string]> = [
  ["episodes", "Low episodes"],
  ["notifications", "Notifications"],
  ["fault", "Sensor fault"],
  ["risk", "Model risk"],
  ["events", "Doses & meals"],
];

export function GlucoseChart({
  view,
  offsetS,
  tauAlert,
  tauWatch,
}: {
  view: PatientView;
  offsetS: number;
  tauAlert: number | null;
  tauWatch: number | null;
}) {
  const [on, setOn] = useState<Record<Layer, boolean>>({
    episodes: true,
    notifications: true,
    fault: true,
    risk: true,
    events: true,
  });
  const option = useMemo<ChartOption>(() => {
    const pts = view.timeline;
    const ms = (ts: number) => (ts + offsetS) * 1000;
    const series = withGaps(pts).map(([t, v]) => [ms(t), v]);
    const maxG = Math.max(250, ...pts.map((p) => p.cgm_mgdl + 20));
    // window: the last 24 h, or since the first reading if the record is younger
    const t0 = ms(Math.max(view.now_ts - 24 * 3600, pts[0]?.ts ?? view.now_ts - 24 * 3600));
    const t1 = ms(view.now_ts);
    const episodes = runs(pts, (p) => p.in_episode).map(([a, b]) => [{ xAxis: ms(a) }, { xAxis: ms(b) + 1 }]);
    const faults = runs(pts, (p) => p.sensor_fault).map(([a, b]) => [{ xAxis: ms(a) }, { xAxis: ms(b) + 1 }]);
    const notes = pts.filter((p) => p.notify).map((p) => [ms(p.ts), p.cgm_mgdl]);
    const risk = pts.map((p) => [ms(p.ts), p.p]);
    const showRisk = on.risk;
    const showEvents = on.events;
    const topH = showRisk ? (showEvents ? "54%" : "62%") : showEvents ? "74%" : "84%";
    const grids: object[] = [{ left: 52, right: 18, top: 14, height: topH }];
    const xAxes: object[] = [
      {
        type: "time",
        gridIndex: 0,
        min: t0,
        max: t1,
        ...AXIS,
        axisLabel: { ...AXIS.axisLabel, show: !showRisk && !showEvents, formatter: (v: number) => clock(v / 1000 - offsetS, offsetS) },
        splitLine: { show: false },
      },
    ];
    const yAxes: object[] = [
      { type: "value", gridIndex: 0, min: 40, max: Math.ceil(maxG / 50) * 50, name: "mg/dL", nameGap: 8, ...AXIS, splitNumber: 4 },
    ];
    const out: object[] = [
      {
        name: "CGM (observed)",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: series,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.75, color: "#1f2937" },
        itemStyle: { color: "#1f2937" },
        markArea: {
          silent: true,
          data: [
            [{ yAxis: 70, itemStyle: { color: "#eef4f2" } }, { yAxis: 180 }],
            ...(on.episodes ? episodes.map(([a, b]) => [{ ...a, itemStyle: { color: "rgba(180,35,24,0.10)" } }, b]) : []),
            ...(on.fault ? faults.map(([a, b]) => [{ ...a, itemStyle: { color: "rgba(124,74,3,0.14)" } }, b]) : []),
          ],
        },
        markLine: {
          silent: true,
          symbol: "none",
          label: { color: "#555e6e", fontSize: 10, position: "insideStartTop" },
          data: [
            { yAxis: 70, lineStyle: { color: "#b42318", type: "dashed", width: 1 }, label: { formatter: "70 mg/dL", position: "insideStartTop", color: "#8f1d14" } },
            { yAxis: 54, lineStyle: { color: "#8f1d14", type: "dotted", width: 1 }, label: { formatter: "54", position: "insideStartBottom", color: "#8f1d14" } },
            { xAxis: t1, lineStyle: { color: "#0e6e6a", width: 1 }, label: { formatter: "now", position: "end", color: "#0e6e6a" } },
          ],
        },
      },
    ];
    if (on.notifications) {
      out.push({
        name: "Notification",
        type: "scatter",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: notes,
        symbol: "triangle",
        symbolSize: 10,
        itemStyle: { color: "#c2410c", borderColor: "#fff", borderWidth: 1 },
        z: 5,
      });
    }
    let gi = 1;
    if (showRisk) {
      grids.push({ left: 52, right: 18, top: showEvents ? "71%" : "80%", height: showEvents ? "15%" : "13%" });
      xAxes.push({
        type: "time",
        gridIndex: gi,
        min: t0,
        max: t1,
        ...AXIS,
        axisLabel: { ...AXIS.axisLabel, show: !showEvents, formatter: (v: number) => clock(v / 1000 - offsetS, offsetS) },
        splitLine: { show: false },
      });
      const pmax = Math.max(tauAlert ?? 0, ...pts.map((p) => p.p ?? 0));
      yAxes.push({
        type: "value",
        gridIndex: gi,
        min: 0,
        max: Math.min(1, Math.ceil(Math.max(0.05, pmax * 1.15) * 10) / 10),
        splitNumber: 2,
        name: "risk",
        nameGap: 6,
        ...AXIS,
        axisLabel: { ...AXIS.axisLabel, formatter: (v: number) => `${Math.round(v * 100)}%` },
      });
      out.push({
        name: "Estimated risk (model)",
        type: "line",
        step: "end",
        xAxisIndex: gi,
        yAxisIndex: gi,
        data: risk,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.25, color: "#0e6e6a" },
        itemStyle: { color: "#0e6e6a" },
        areaStyle: { color: "rgba(14,110,106,0.08)" },
        markLine: {
          silent: true,
          symbol: "none",
          label: { fontSize: 10, color: "#555e6e", position: "insideEndTop" },
          data: [
            ...(tauAlert !== null ? [{ yAxis: tauAlert, lineStyle: { color: "#c2410c", type: "dashed", width: 1 }, label: { formatter: "ALERT τ" } }] : []),
            ...(tauWatch !== null ? [{ yAxis: tauWatch, lineStyle: { color: "#a16207", type: "dotted", width: 1 }, label: { formatter: "WATCH τ", position: "insideEndBottom" } }] : []),
          ],
        },
      });
      gi += 1;
    }
    if (showEvents) {
      grids.push({ left: 52, right: 18, top: "87%", height: "8%" });
      xAxes.push({
        type: "time",
        gridIndex: gi,
        min: t0,
        max: t1,
        ...AXIS,
        axisLabel: { ...AXIS.axisLabel, formatter: (v: number) => clock(v / 1000 - offsetS, offsetS) },
        splitLine: { show: false },
      });
      yAxes.push({ type: "category", gridIndex: gi, data: ["Meal", "Dose"], ...AXIS, axisLabel: { ...AXIS.axisLabel, fontSize: 10, interval: 0 }, splitLine: { show: false } });
      out.push({
        name: "Recorded dose",
        type: "scatter",
        xAxisIndex: gi,
        yAxisIndex: gi,
        data: view.doses.map((d) => ({ value: [ms(d.ts), "Dose"], dose: d })),
        symbol: "rect",
        symbolSize: [3, 11],
        itemStyle: { color: "#2f6fd6" },
      });
      out.push({
        name: "Recorded meal",
        type: "scatter",
        xAxisIndex: gi,
        yAxisIndex: gi,
        data: view.meals.map((t) => [ms(t), "Meal"]),
        symbol: "circle",
        symbolSize: 6,
        itemStyle: { color: "#9aa3b2" },
      });
    }
    return {
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      series: out,
      axisPointer: { link: [{ xAxisIndex: "all" }], lineStyle: { color: "#9aa3b2" } },
      tooltip: {
        ...TOOLTIP,
        trigger: "axis",
        formatter: (items: Array<{ seriesName: string; value: [number, number | string | null]; data: { dose?: { canonical?: string; dose?: number; dose_unit?: string } } }>) => {
          if (!items.length) return "";
          const t = items[0]!.value[0] / 1000 - offsetS;
          const rows = items
            .filter((i) => i.value[1] !== null)
            .map((i) => {
              const v = i.value[1];
              if (i.seriesName === "Estimated risk (model)") return `Estimated risk: <b>${(Number(v) * 100).toFixed(1)}%</b>`;
              if (i.seriesName === "CGM (observed)") return `CGM: <b>${Math.round(Number(v))} mg/dL</b>`;
              if (i.seriesName === "Recorded dose") {
                const d = i.data.dose;
                return `Dose: <b>${d?.canonical ?? "unknown"}</b>${d?.dose ? ` ${d.dose} ${d.dose_unit ?? ""}` : ""}`;
              }
              return i.seriesName;
            });
          return [`<span style="color:#555e6e">${clock(t, offsetS)}</span>`, ...rows].join("<br/>");
        },
      },
    };
  }, [view, offsetS, tauAlert, tauWatch, on]);

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1.5" role="group" aria-label="Chart layers">
        {LAYERS.map(([k, label]) => (
          <button
            key={k}
            type="button"
            aria-pressed={on[k]}
            onClick={() => setOn({ ...on, [k]: !on[k] })}
            className={clsx(
              "h-6 rounded-sm border px-2 text-[11.5px] font-medium",
              on[k] ? "border-line-strong bg-surface text-ink" : "border-line bg-sunken text-ink-4",
            )}
          >
            {label}
          </button>
        ))}
        <span className="ml-auto text-[11px] text-ink-4">Last 24 h · record’s local clock · gaps &gt; 20 min not joined</span>
      </div>
      <Chart
        option={option}
        height={380}
        label={`CGM over the last 24 hours with ${view.timeline.filter((p) => p.notify).length} notifications`}
      />
    </div>
  );
}
