import type {
  DayRow,
  DayStationProps,
  FeatureCollection,
  HourRow,
  LineRow,
  LiveStationProps,
  LiveSummary,
  Mode,
  ModeRow,
  PulsePoint,
  StationDetail,
  StationRow,
  Status,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

type Params = Record<string, string | number | null | undefined>;

async function get<T>(path: string, params: Params = {}, signal?: AbortSignal): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null && v !== "") qs.set(k, String(v));
  const url = `${BASE}/api/${path}${qs.size ? `?${qs}` : ""}`;
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  status: (s?: AbortSignal) => get<Status>("status", {}, s),
  liveSummary: (s?: AbortSignal) => get<LiveSummary | null>("live/summary", {}, s),
  livePulse: (hours: number, s?: AbortSignal) => get<PulsePoint[]>("live/pulse", { hours }, s),
  liveMap: (s?: AbortSignal) => get<FeatureCollection<LiveStationProps>>("live/map", {}, s),
  days: (mode: Mode | null, s?: AbortSignal) => get<DayRow[]>("history/days", { mode, limit: 60 }, s),
  modes: (day: string, s?: AbortSignal) => get<ModeRow[]>("history/modes", { day }, s),
  hours: (day: string, mode: Mode | null, s?: AbortSignal) =>
    get<HourRow[]>("history/hours", { day, mode }, s),
  lines: (day: string, mode: Mode | null, s?: AbortSignal) =>
    get<LineRow[]>("history/lines", { day, mode, limit: 8 }, s),
  stations: (day: string, mode: Mode | null, s?: AbortSignal) =>
    get<StationRow[]>("history/stations", { day, mode, limit: 8, min_measured: 100 }, s),
  dayMap: (day: string, mode: Mode | null, s?: AbortSignal) =>
    get<FeatureCollection<DayStationProps>>("history/map", { day, mode }, s),
  search: (q: string, s?: AbortSignal) => get<{ uic: number; name: string }[]>("stations/search", { q }, s),
  station: (uic: number, s?: AbortSignal) => get<StationDetail>(`stations/${uic}`, {}, s),
};
