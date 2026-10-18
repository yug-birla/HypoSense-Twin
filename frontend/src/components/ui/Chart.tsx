"use client";
import { BarChart, CustomChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([
  LineChart,
  ScatterChart,
  BarChart,
  CustomChart,
  GridComponent,
  TooltipComponent,
  MarkAreaComponent,
  MarkLineComponent,
  LegendComponent,
  DataZoomComponent,
  SVGRenderer,
]);

export type ChartOption = echarts.EChartsCoreOption;

/** Shared chart text style (design tokens). */
export const AXIS = {
  axisLine: { lineStyle: { color: "#cbd1d9" } },
  axisTick: { show: false },
  axisLabel: { color: "#555e6e", fontSize: 11, fontFamily: "Inter Variable, sans-serif" },
  splitLine: { lineStyle: { color: "#eceff3" } },
  nameTextStyle: { color: "#555e6e", fontSize: 11 },
};

export const TOOLTIP = {
  backgroundColor: "#ffffff",
  borderColor: "#e3e6eb",
  borderWidth: 1,
  padding: [6, 9],
  textStyle: { color: "#3f4857", fontSize: 12, fontFamily: "Inter Variable, sans-serif" },
  extraCssText: "box-shadow: 0 4px 16px rgba(16,24,40,0.08); border-radius: 6px;",
};

export function Chart({
  option,
  height,
  label,
}: {
  option: ChartOption;
  height: number;
  label: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const inst = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!el.current) return;
    const c = echarts.init(el.current, undefined, { renderer: "svg" });
    inst.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      c.dispose();
      inst.current = null;
    };
  }, []);

  useEffect(() => {
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    inst.current?.setOption({ animation: !reduce, animationDuration: 250, ...option }, { notMerge: true });
  }, [option]);

  return <div ref={el} role="img" aria-label={label} style={{ height }} className="w-full" />;
}
