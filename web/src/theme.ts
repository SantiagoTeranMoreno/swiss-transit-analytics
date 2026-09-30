/**
 * Colours. Chrome and series colours live as CSS custom properties in styles.css
 * (light and dark are separate, validated steps); canvas charts and the map read
 * them from there. Status colours are the same in both modes.
 */

export const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
  none: "#898781",
} as const;
export type StatusKey = keyof typeof STATUS;

export interface Bin {
  key: StatusKey;
  label: string;
}

/** Live station colour: average predicted delay of upcoming departures. */
export const LIVE_BINS: (Bin & { max: number })[] = [
  { key: "good", label: "< 1 min", max: 60 },
  { key: "warning", label: "1–3 min", max: 180 },
  { key: "serious", label: "3–5 min", max: 300 },
  { key: "critical", label: "5 min +", max: Infinity },
];

/** Historical station colour: share of arrivals less than 3 minutes late. */
export const DAY_BINS: (Bin & { min: number })[] = [
  { key: "good", label: "≥ 95%", min: 0.95 },
  { key: "warning", label: "90–95%", min: 0.9 },
  { key: "serious", label: "80–90%", min: 0.8 },
  { key: "critical", label: "< 80%", min: -Infinity },
];

export function liveStatus(avgDelayS: number | null | undefined): StatusKey {
  if (avgDelayS == null) return "none";
  return LIVE_BINS.find((b) => avgDelayS < b.max)!.key;
}

export function dayStatus(punctuality: number | null | undefined): StatusKey {
  if (punctuality == null) return "none";
  return DAY_BINS.find((b) => punctuality >= b.min)!.key;
}

/** Freshness of the live feed: minutes since the latest snapshot. */
export function freshness(ageMin: number): { key: StatusKey; label: string } {
  if (ageMin <= 15) return { key: "good", label: "Live" };
  if (ageMin <= 60) return { key: "warning", label: "Delayed" };
  return { key: "critical", label: "Stale" };
}

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export interface ChartTheme {
  series: string;
  muted: string;
  text: string;
  text2: string;
  grid: string;
  axis: string;
  surface: string;
  selectedFade: string;
}

export function chartTheme(): ChartTheme {
  return {
    series: cssVar("--series-1"),
    muted: cssVar("--text-muted"),
    text: cssVar("--text-primary"),
    text2: cssVar("--text-secondary"),
    grid: cssVar("--gridline"),
    axis: cssVar("--baseline"),
    surface: cssVar("--surface-1"),
    selectedFade: cssVar("--series-fade"),
  };
}
