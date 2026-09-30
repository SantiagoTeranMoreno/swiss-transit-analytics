export const MODES = ["rail", "bus", "tram", "metro", "ship", "cableway", "other"] as const;
export type Mode = (typeof MODES)[number];

/** Counters and ratios shared by every historical aggregate. Ratios are 0..1. */
export interface Ratios {
  events: number;
  measured: number;
  punctuality: number | null;
  share_delayed_5min: number | null;
  share_cancelled: number | null;
  avg_delay_s: number | null;
}

export interface Status {
  days: string[];
  latest_day: string | null;
  live_observed_at: string | null;
  last_runs: Record<string, { source: string; finished_at: string; resource_key: string | null }>;
}

export interface LiveSummary {
  observed_at: string;
  trips: number;
  trips_cancelled: number;
  stop_updates: number;
  avg_delay_s: number | null;
  share_delayed_3min: number | null;
  stations: number;
  stations_with_delays: number;
}

export interface PulsePoint {
  observed_at: string;
  trips: number;
  trips_cancelled: number;
  avg_delay_s: number | null;
  share_delayed_3min: number | null;
}

export type DayRow = Ratios & { service_day: string };
export type ModeRow = Ratios & { transport_mode: Mode };
export type HourRow = Ratios & { hour_of_day: number };
export type LineRow = Ratios & {
  operator_abbr: string;
  line_text: string;
  transport_mode: Mode;
  trips: number;
  delay_max_s: number;
};
export type StationRow = Ratios & { uic: number; name: string | null; delay_max_s: number };

export interface LiveStationProps {
  uic: number;
  name: string;
  upcoming_events: number;
  avg_delay_s: number | null;
  max_delay_s: number | null;
  delayed_3min: number;
  skipped: number;
}

export interface DayStationProps {
  uic: number;
  name: string;
  measured: number;
  punctuality: number | null;
  avg_delay_s: number | null;
}

export interface FeatureCollection<P> {
  type: "FeatureCollection";
  features: { type: "Feature"; geometry: { type: "Point"; coordinates: [number, number] }; properties: P }[];
}

export interface StationDetail {
  uic: number;
  name: string;
  lon: number;
  lat: number;
  live: Omit<LiveStationProps, "uic" | "name"> & { observed_at: string } | null;
  history: DayRow[];
  modes: ModeRow[];
}
