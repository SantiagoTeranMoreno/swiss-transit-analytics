/** ECharts option builders. Every chart: one y-scale, thin marks, hairline grid, hover tooltip. */
import type { EChartsOption } from "./components/Chart";
import { clock, dayLabel, dayTime, delay, int, MODE_LABEL, pct } from "./format";
import type { ChartTheme } from "./theme";
import type { DayRow, HourRow, ModeRow, PulsePoint } from "./types";

const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif';

function base(t: ChartTheme): EChartsOption {
  return {
    animationDuration: 300,
    textStyle: { fontFamily: FONT, color: t.text2 },
    tooltip: {
      trigger: "axis",
      backgroundColor: t.surface,
      borderColor: t.grid,
      textStyle: { color: t.text, fontFamily: FONT, fontSize: 12 },
      axisPointer: { type: "line", lineStyle: { color: t.axis } },
    },
  };
}

function valueAxis(t: ChartTheme, extra: Record<string, unknown> = {}) {
  return {
    type: "value",
    splitLine: { lineStyle: { color: t.grid } },
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: t.muted, fontSize: 11 },
    ...extra,
  };
}

function categoryAxis(t: ChartTheme, data: string[], extra: Record<string, unknown> = {}) {
  return {
    type: "category",
    data,
    axisLine: { lineStyle: { color: t.axis } },
    axisTick: { show: false },
    axisLabel: { color: t.muted, fontSize: 11 },
    ...extra,
  };
}

const percentAxis = (v: number) => `${Math.round(v * 100)}%`;

// A gap longer than this between live snapshots is drawn as a break in the line.
const PULSE_GAP_MS = 25 * 60_000;

/** Share of upcoming stops predicted ≥ 3 min late, per live snapshot. */
export function pulseOption(points: PulsePoint[], t: ChartTheme): EChartsOption {
  const data: ([number, number | null] | [number, null])[] = [];
  points.forEach((p, i) => {
    const ts = new Date(p.observed_at).getTime();
    if (i > 0 && ts - new Date(points[i - 1].observed_at).getTime() > PULSE_GAP_MS) {
      data.push([ts - 1, null]);
    }
    data.push([ts, p.share_delayed_3min]);
  });
  const byTs = new Map(points.map((p) => [new Date(p.observed_at).getTime(), p]));
  return {
    ...base(t),
    grid: { left: 44, right: 16, top: 12, bottom: 28 },
    xAxis: {
      type: "time",
      axisLine: { lineStyle: { color: t.axis } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { color: t.muted, fontSize: 11, formatter: (v: number) => clock(new Date(v).toISOString()) },
    },
    yAxis: valueAxis(t, { min: 0, axisLabel: { color: t.muted, fontSize: 11, formatter: percentAxis } }),
    tooltip: {
      ...(base(t).tooltip as object),
      formatter: (params: { value: [number, number | null] }[]) => {
        const p = byTs.get(params[0]?.value[0]);
        if (!p) return "";
        return `<b>${dayTime(p.observed_at)}</b><br/>${pct(p.share_delayed_3min)} of stops ≥ 3 min late<br/>Average delay ${delay(p.avg_delay_s)}<br/>${int(p.trips)} trips, ${int(p.trips_cancelled)} cancelled`;
      },
    },
    series: [
      {
        type: "line",
        data,
        connectNulls: false,
        showSymbol: true,
        symbolSize: 8,
        lineStyle: { width: 2, color: t.series },
        itemStyle: { color: t.series, borderColor: t.surface, borderWidth: 2 },
      },
    ],
  };
}

/** Punctuality per hour of the day (line: the y-axis does not start at zero). */
export function hoursOption(rows: HourRow[], t: ChartTheme): EChartsOption {
  const hours = Array.from({ length: 24 }, (_, h) => h);
  const byHour = new Map(rows.map((r) => [r.hour_of_day, r]));
  return {
    ...base(t),
    grid: { left: 44, right: 16, top: 12, bottom: 28 },
    xAxis: categoryAxis(t, hours.map((h) => `${String(h).padStart(2, "0")}h`), {
      boundaryGap: false,
      axisLabel: { color: t.muted, fontSize: 11, interval: 2 },
    }),
    yAxis: valueAxis(t, { scale: true, max: 1, splitNumber: 4, axisLabel: { color: t.muted, fontSize: 11, formatter: percentAxis } }),
    tooltip: {
      ...(base(t).tooltip as object),
      formatter: (params: { dataIndex: number }[]) => {
        const r = byHour.get(params[0]?.dataIndex);
        if (!r) return "";
        return `<b>${String(r.hour_of_day).padStart(2, "0")}:00–${String(r.hour_of_day).padStart(2, "0")}:59</b><br/>${pct(r.punctuality)} on time<br/>Average delay ${delay(r.avg_delay_s)}<br/>${int(r.measured)} measured arrivals`;
      },
    },
    series: [
      {
        type: "line",
        data: hours.map((h) => byHour.get(h)?.punctuality ?? null),
        connectNulls: false,
        showSymbol: false,
        symbolSize: 8,
        lineStyle: { width: 2, color: t.series },
        itemStyle: { color: t.series },
        areaStyle: { color: t.selectedFade },
      },
    ],
  };
}

/** Punctuality per transport mode; the selected mode keeps full colour. */
export function modesOption(rows: ModeRow[], selected: string | null, t: ChartTheme): EChartsOption {
  const sorted = [...rows].filter((r) => r.measured > 0).reverse();
  return {
    ...base(t),
    grid: { left: 72, right: 52, top: 4, bottom: 4 },
    xAxis: valueAxis(t, { min: 0, max: 1, show: false }),
    yAxis: categoryAxis(t, sorted.map((r) => MODE_LABEL[r.transport_mode]), {
      axisLine: { show: false },
      axisLabel: { color: t.text2, fontSize: 12 },
    }),
    tooltip: {
      ...(base(t).tooltip as object),
      axisPointer: { type: "none" },
      formatter: (params: { dataIndex: number }[]) => {
        const r = sorted[params[0]?.dataIndex];
        if (!r) return "";
        return `<b>${MODE_LABEL[r.transport_mode]}</b><br/>${pct(r.punctuality)} on time<br/>Average delay ${delay(r.avg_delay_s)}<br/>${int(r.measured)} measured arrivals<br/><span style="opacity:.7">Click to filter</span>`;
      },
    },
    series: [
      {
        type: "bar",
        barWidth: 14,
        cursor: "pointer",
        data: sorted.map((r) => ({
          value: r.punctuality,
          itemStyle: {
            color: !selected || selected === r.transport_mode ? t.series : t.selectedFade,
            borderRadius: [0, 4, 4, 0],
          },
        })),
        label: {
          show: true,
          position: "right",
          color: t.text2,
          fontSize: 12,
          formatter: (p: { value: number }) => pct(p.value),
        },
      },
    ],
  };
}

/** National punctuality per service day; the selected day is marked. */
export function daysOption(rows: DayRow[], selected: string | null, t: ChartTheme): EChartsOption {
  return {
    ...base(t),
    grid: { left: 44, right: 16, top: 12, bottom: 28 },
    xAxis: categoryAxis(t, rows.map((r) => r.service_day), {
      boundaryGap: rows.length < 3,
      axisLabel: { color: t.muted, fontSize: 11, formatter: (v: string) => dayLabel(v, "short") },
    }),
    yAxis: valueAxis(t, { scale: true, splitNumber: 4, axisLabel: { color: t.muted, fontSize: 11, formatter: percentAxis } }),
    tooltip: {
      ...(base(t).tooltip as object),
      formatter: (params: { dataIndex: number }[]) => {
        const r = rows[params[0]?.dataIndex];
        if (!r) return "";
        return `<b>${dayLabel(r.service_day)}</b><br/>${pct(r.punctuality)} on time<br/>${pct(r.share_cancelled)} cancelled<br/>${int(r.measured)} measured arrivals<br/><span style="opacity:.7">Click to select this day</span>`;
      },
    },
    series: [
      {
        type: "line",
        cursor: "pointer",
        symbol: "circle",
        data: rows.map((r) => ({
          value: r.punctuality,
          symbolSize: r.service_day === selected ? 12 : 7,
        })),
        showSymbol: true,
        lineStyle: { width: 2, color: t.series },
        itemStyle: { color: t.series, borderColor: t.surface, borderWidth: 2 },
      },
    ],
  };
}

/** Daily punctuality of one station (small multiple in the station panel). */
export function stationDaysOption(rows: DayRow[], t: ChartTheme): EChartsOption {
  const opt = daysOption(rows, rows.at(-1)?.service_day ?? null, t);
  return { ...opt, grid: { left: 40, right: 8, top: 8, bottom: 24 } };
}
