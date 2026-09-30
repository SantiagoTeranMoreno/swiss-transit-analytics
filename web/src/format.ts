import type { Mode } from "./types";

export const MODE_LABEL: Record<Mode, string> = {
  rail: "Train",
  bus: "Bus",
  tram: "Tram",
  metro: "Metro",
  ship: "Boat",
  cableway: "Cableway",
  other: "Other",
};

export const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "–" : `${(v * 100).toFixed(digits)}%`;

export const int = (v: number | null | undefined) => (v == null ? "–" : Math.round(v).toLocaleString("en-US"));

/** Seconds as "1 min 25 s" / "45 s". */
export function delay(s: number | null | undefined): string {
  if (s == null) return "–";
  const r = Math.round(s);
  if (Math.abs(r) < 60) return `${r} s`;
  const m = Math.floor(r / 60);
  const rest = r % 60;
  return rest ? `${m} min ${rest} s` : `${m} min`;
}

const ZURICH_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Zurich",
  hour: "2-digit",
  minute: "2-digit",
});
const ZURICH_DAY_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Zurich",
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export const clock = (iso: string) => ZURICH_TIME.format(new Date(iso));
export const dayTime = (iso: string) => ZURICH_DAY_TIME.format(new Date(iso));

export function dayLabel(day: string, style: "long" | "short" = "long"): string {
  const d = new Date(`${day}T12:00:00Z`);
  return d.toLocaleDateString("en-GB", {
    weekday: style === "long" ? "long" : "short",
    day: "numeric",
    month: style === "long" ? "long" : "short",
    timeZone: "UTC",
  });
}

export function ago(iso: string, now: number): string {
  const min = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60_000));
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.floor(min / 60);
  if (h < 48) return `${h} h ${min % 60} min ago`;
  return `${Math.floor(h / 24)} days ago`;
}
