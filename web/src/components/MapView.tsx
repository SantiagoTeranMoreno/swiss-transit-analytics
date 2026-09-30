import maplibregl, { type ExpressionSpecification, type GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import { delay, int, pct } from "../format";
import { DAY_BINS, LIVE_BINS, STATUS } from "../theme";
import type { DayStationProps, FeatureCollection, LiveStationProps } from "../types";

export type MapLayer = "live" | "day";

const STYLE = {
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
};
const SWITZERLAND: [number, number, number, number] = [5.9, 45.8, 10.5, 47.85];

// Same bins as the legend (theme.ts), as MapLibre "step" expressions.
const LIVE_COLOR: ExpressionSpecification = [
  "case",
  ["==", ["get", "avg_delay_s"], null],
  STATUS.none,
  [
    "step",
    ["get", "avg_delay_s"],
    STATUS[LIVE_BINS[0].key],
    LIVE_BINS[0].max,
    STATUS[LIVE_BINS[1].key],
    LIVE_BINS[1].max,
    STATUS[LIVE_BINS[2].key],
    LIVE_BINS[2].max,
    STATUS[LIVE_BINS[3].key],
  ],
];
const DAY_COLOR: ExpressionSpecification = [
  "step",
  ["get", "punctuality"],
  STATUS[DAY_BINS[3].key],
  DAY_BINS[2].min,
  STATUS[DAY_BINS[2].key],
  DAY_BINS[1].min,
  STATUS[DAY_BINS[1].key],
  DAY_BINS[0].min,
  STATUS[DAY_BINS[0].key],
];

const SIZE_FIELD: Record<MapLayer, string> = { live: "upcoming_events", day: "measured" };

function radius(layer: MapLayer, extra = 0): ExpressionSpecification {
  // Busier stations draw slightly bigger; everything grows with zoom.
  const busy: ExpressionSpecification = ["min", 1, ["/", ["ln", ["+", 1, ["get", SIZE_FIELD[layer]]]], 7]];
  return [
    "interpolate",
    ["linear"],
    ["zoom"],
    6,
    ["+", 1.5 + extra, ["*", 2.5, busy]],
    10,
    ["+", 3 + extra, ["*", 5, busy]],
    14,
    ["+", 5 + extra, ["*", 8, busy]],
  ];
}

function tooltip(layer: MapLayer, p: Record<string, unknown>): string {
  const name = String(p.name ?? "");
  if (layer === "live") {
    const l = p as unknown as LiveStationProps;
    return `<b>${name}</b><br/>Average delay ${delay(l.avg_delay_s)}<br/>${int(l.delayed_3min)} of ${int(l.upcoming_events)} upcoming stops ≥ 3 min late${l.skipped ? `<br/>${int(l.skipped)} skipped` : ""}`;
  }
  const d = p as unknown as DayStationProps;
  return `<b>${name}</b><br/>${pct(d.punctuality)} on time<br/>Average delay ${delay(d.avg_delay_s)}<br/>${int(d.measured)} measured arrivals`;
}

interface Props {
  layer: MapLayer;
  data: FeatureCollection<LiveStationProps> | FeatureCollection<DayStationProps> | undefined;
  dark: boolean;
  selected: { uic: number; lon: number; lat: number } | null;
  onSelect: (uic: number) => void;
}

export function MapView({ layer, data, dark, selected, onSelect }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const latest = useRef({ layer, data, onSelect });
  latest.current = { layer, data, onSelect };

  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current!,
      style: dark ? STYLE.dark : STYLE.light,
      bounds: SWITZERLAND,
      fitBoundsOptions: { padding: 16 },
      attributionControl: { compact: true, customAttribution: "Transit data © opentransportdata.swiss" },
      cooperativeGestures: window.matchMedia("(pointer: coarse)").matches,
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: "map-tip" });

    m.on("load", () => {
      m.addSource("stations", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({
        id: "stations",
        type: "circle",
        source: "stations",
        paint: {
          "circle-color": LIVE_COLOR,
          "circle-radius": radius("live"),
          "circle-opacity": 0.9,
          "circle-stroke-color": dark ? "#1a1a19" : "#ffffff",
          "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 6, 0.5, 10, 1.5],
        },
      });
      m.addLayer({
        id: "selected",
        type: "circle",
        source: "stations",
        filter: ["==", ["get", "uic"], -1],
        paint: {
          "circle-color": "rgba(0,0,0,0)",
          "circle-radius": radius("live", 5),
          "circle-stroke-color": dark ? "#ffffff" : "#0b0b0b",
          "circle-stroke-width": 2,
        },
      });
      ready.current = true;
      apply();
    });

    m.on("mousemove", "stations", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      m.getCanvas().style.cursor = "pointer";
      popup
        .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
        .setHTML(tooltip(latest.current.layer, f.properties))
        .addTo(m);
    });
    m.on("mouseleave", "stations", () => {
      m.getCanvas().style.cursor = "";
      popup.remove();
    });
    m.on("click", "stations", (e) => {
      const uic = e.features?.[0]?.properties?.uic;
      if (uic != null) latest.current.onSelect(Number(uic));
    });

    return () => {
      ready.current = false;
      m.remove();
      map.current = null;
    };
    // The basemap style is fixed per mount: App remounts the map when the colour scheme changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function apply() {
    const m = map.current;
    if (!m || !ready.current) return;
    const { layer: l, data: d } = latest.current;
    (m.getSource("stations") as GeoJSONSource).setData(
      (d ?? { type: "FeatureCollection", features: [] }) as GeoJSON.FeatureCollection,
    );
    m.setPaintProperty("stations", "circle-color", l === "live" ? LIVE_COLOR : DAY_COLOR);
    m.setPaintProperty("stations", "circle-radius", radius(l));
    m.setPaintProperty("selected", "circle-radius", radius(l, 5));
  }

  useEffect(apply, [layer, data]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const setFilter = () => m.setFilter("selected", ["==", ["get", "uic"], selected?.uic ?? -1]);
    if (ready.current) setFilter();
    else m.once("load", setFilter);
    if (selected) m.easeTo({ center: [selected.lon, selected.lat], zoom: Math.max(m.getZoom(), 11) });
  }, [selected]);

  return <div ref={el} className="map" />;
}
