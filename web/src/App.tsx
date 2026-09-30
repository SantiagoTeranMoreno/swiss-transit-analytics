import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { daysOption, hoursOption, modesOption, pulseOption } from "./charts";
import { Chart } from "./components/Chart";
import { MapView, type MapLayer } from "./components/MapView";
import { LineRanking, StationRanking } from "./components/Ranking";
import { Search } from "./components/Search";
import { StationPanel } from "./components/StationPanel";
import { Card, Empty, Segmented, Stat, StatusDot } from "./components/ui";
import { ago, clock, dayLabel, dayTime, delay, int, MODE_LABEL, pct } from "./format";
import { useDarkMode, useData, useNow } from "./hooks";
import { chartTheme, DAY_BINS, freshness, LIVE_BINS, STATUS } from "./theme";
import type { Mode } from "./types";

const LIVE_REFRESH_MS = 60_000;
const PULSE_HOURS = 24;

export function App() {
  const dark = useDarkMode();
  const now = useNow();
  const [day, setDay] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode | null>(null);
  const [layer, setLayer] = useState<MapLayer>("live");
  const [uic, setUic] = useState<number | null>(null);

  const status = useData((s) => api.status(s), [], LIVE_REFRESH_MS);
  const summary = useData((s) => api.liveSummary(s), [], LIVE_REFRESH_MS);
  const pulse = useData((s) => api.livePulse(PULSE_HOURS, s), [], LIVE_REFRESH_MS);
  const liveMap = useData(layer === "live" ? (s) => api.liveMap(s) : null, [layer], LIVE_REFRESH_MS);

  const selectedDay = day ?? status.data?.latest_day ?? null;
  const d = selectedDay;
  const days = useData((s) => api.days(mode, s), [mode]);
  const modes = useData(d ? (s) => api.modes(d, s) : null, [d]);
  const hours = useData(d ? (s) => api.hours(d, mode, s) : null, [d, mode]);
  const lines = useData(d ? (s) => api.lines(d, mode, s) : null, [d, mode]);
  const stations = useData(d ? (s) => api.stations(d, mode, s) : null, [d, mode]);
  const dayMap = useData(d && layer === "day" ? (s) => api.dayMap(d, mode, s) : null, [d, mode, layer]);
  const station = useData(uic != null ? (s) => api.station(uic, s) : null, [uic], LIVE_REFRESH_MS);

  // Charts draw on canvas, so they read theme colours explicitly and rebuild on scheme change.
  const theme = useMemo(() => chartTheme(), [dark]); // eslint-disable-line react-hooks/exhaustive-deps
  const pulseOpt = useMemo(() => pulseOption(pulse.data ?? [], theme), [pulse.data, theme]);
  const daysOpt = useMemo(() => daysOption(days.data ?? [], selectedDay, theme), [days.data, selectedDay, theme]);
  const hoursOpt = useMemo(() => hoursOption(hours.data ?? [], theme), [hours.data, theme]);
  const modesOpt = useMemo(() => modesOption(modes.data ?? [], mode, theme), [modes.data, mode, theme]);

  const dayRow = days.data?.find((r) => r.service_day === selectedDay);
  const live = summary.data;
  const ageMin = live ? (now - new Date(live.observed_at).getTime()) / 60_000 : Infinity;
  const fresh = freshness(ageMin);
  const errors = [status, summary].map((x) => x.error).filter(Boolean);

  useEffect(() => {
    if (uic != null && station.error) setUic(null);
  }, [station.error, uic]);

  const availableModes = (modes.data ?? []).filter((m) => m.measured > 0).map((m) => m.transport_mode);
  const selected = station.data ? { uic: station.data.uic, lon: station.data.lon, lat: station.data.lat } : null;

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>How punctual is Swiss public transport?</h1>
          <p className="sub">
            Every train, tram, bus and boat in Switzerland: live delay predictions and measured punctuality
            (arrivals less than 3 minutes late), from open data.
          </p>
        </div>
        <div className="fresh" title={live ? `Latest live snapshot: ${dayTime(live.observed_at)}` : undefined}>
          {live ? (
            <>
              <StatusDot status={fresh.key} label={fresh.label} />
              <span>
                Live data from <b>{clock(live.observed_at)}</b> <span className="muted">({ago(live.observed_at, now)})</span>
              </span>
            </>
          ) : (
            <span className="muted">{summary.loading ? "Connecting…" : "No live data yet"}</span>
          )}
        </div>
      </header>

      {errors.length > 0 && (
        <div className="banner" role="alert">
          The data service is not answering ({errors[0]}). It may be waking up; the page retries every minute.
        </div>
      )}
      {live && fresh.key === "critical" && (
        <div className="banner soft">
          The live feed was last refreshed {ago(live.observed_at, now)}, so the live view shows that moment rather
          than right now.
        </div>
      )}

      <div className="filters">
        <label className="field">
          <span>Day</span>
          <select value={selectedDay ?? ""} onChange={(e) => setDay(e.target.value)} disabled={!status.data?.days.length}>
            {status.data?.days.map((dd) => (
              <option key={dd} value={dd}>
                {dayLabel(dd)}
              </option>
            ))}
          </select>
        </label>
        <div className="field">
          <span>Transport</span>
          <Segmented
            label="Transport mode"
            value={mode ?? "all"}
            onChange={(v) => setMode(v === "all" ? null : (v as Mode))}
            options={[
              { value: "all", label: "All" },
              ...availableModes.map((m) => ({ value: m, label: MODE_LABEL[m] })),
            ]}
          />
        </div>
      </div>

      <section className="kpis">
        <Stat
          label="Stops ≥ 3 min late, live"
          value={pct(live?.share_delayed_3min)}
          note={live ? `of upcoming stops at ${clock(live.observed_at)}` : "–"}
        />
        <Stat label="Average delay, live" value={delay(live?.avg_delay_s)} note={live ? `${int(live.trips)} trips in the feed` : "–"} />
        <Stat
          label="Trips cancelled, live"
          value={int(live?.trips_cancelled)}
          note={live ? `${int(live.stations_with_delays)} stations with delays` : "–"}
        />
        <Stat
          label={`On time${mode ? `, ${MODE_LABEL[mode].toLowerCase()}` : ""}`}
          value={pct(dayRow?.punctuality)}
          note={selectedDay ? dayLabel(selectedDay) : "–"}
        />
        <Stat
          label="Cancelled"
          value={pct(dayRow?.share_cancelled, 2)}
          note={dayRow ? `${int(dayRow.events)} planned stops` : "–"}
        />
      </section>

      <div className="main-grid">
        <Card
          className="map-card"
          title={layer === "live" ? "Live delays by station" : `Punctuality by station, ${selectedDay ? dayLabel(selectedDay, "short") : ""}`}
          subtitle={
            layer === "live"
              ? "Average predicted delay of upcoming stops. Click a station for details."
              : "Share of measured arrivals less than 3 minutes late."
          }
          actions={
            <Segmented
              label="Map layer"
              value={layer}
              onChange={setLayer}
              options={[
                { value: "live", label: "Live" },
                { value: "day", label: "By day" },
              ]}
            />
          }
        >
          <div className="map-wrap">
            <MapView
              key={dark ? "dark" : "light"}
              layer={layer}
              data={layer === "live" ? liveMap.data : dayMap.data}
              dark={dark}
              selected={selected}
              onSelect={setUic}
            />
            <div className="legend" aria-label="Map legend">
              {(layer === "live" ? LIVE_BINS : DAY_BINS).map((b) => (
                <span key={b.key} className="legend-item">
                  <span className="swatch" style={{ background: STATUS[b.key] }} />
                  {b.label}
                </span>
              ))}
              {layer === "live" && (
                <span className="legend-item">
                  <span className="swatch" style={{ background: STATUS.none }} />
                  Skipped only
                </span>
              )}
            </div>
          </div>
        </Card>

        <aside className="card side">
          <Search onSelect={setUic} />
          {station.data && uic != null ? (
            <StationPanel station={station.data} now={now} dark={dark} onClose={() => setUic(null)} />
          ) : (
            <>
              <h2 className="side-title">Least punctual stations</h2>
              <p className="sub">
                {selectedDay ? dayLabel(selectedDay) : ""}
                {mode ? `, ${MODE_LABEL[mode].toLowerCase()}` : ""} · at least 100 measured arrivals
              </p>
              <StationRanking rows={stations.data} onSelect={setUic} />
            </>
          )}
        </aside>
      </div>

      <div className="chart-grid">
        <Card title="Live delay, last 24 hours" subtitle="Share of upcoming stops predicted ≥ 3 min late, per live snapshot. Gaps: no snapshot.">
          {pulse.data?.length ? (
            <Chart option={pulseOpt} height={220} label="Share of stops at least 3 minutes late over the last 24 hours" />
          ) : (
            <Empty>No live snapshots in the last 24 hours.</Empty>
          )}
        </Card>

        <Card title="Punctuality per day" subtitle={`Share of arrivals < 3 min late${mode ? `, ${MODE_LABEL[mode].toLowerCase()}` : ""}. Click a day to select it.`}>
          {days.data?.length ? (
            <Chart
              option={daysOpt}
              height={220}
              label="Punctuality per day"
              onClick={(p) => days.data && setDay(days.data[p.dataIndex].service_day)}
            />
          ) : (
            <Empty>No measured days loaded yet.</Empty>
          )}
        </Card>

        <Card title="Punctuality by hour" subtitle={`${selectedDay ? dayLabel(selectedDay) : ""}${mode ? `, ${MODE_LABEL[mode].toLowerCase()}` : ""}`}>
          {hours.data?.length ? (
            <Chart option={hoursOpt} height={220} label="Punctuality by hour of the day" />
          ) : (
            <Empty>No data for this day.</Empty>
          )}
        </Card>

        <Card title="Punctuality by transport mode" subtitle="Click a bar to filter the whole page.">
          {modes.data?.length ? (
            <Chart
              option={modesOpt}
              height={220}
              label="Punctuality by transport mode"
              onClick={(p) => {
                const sorted = (modes.data ?? []).filter((r) => r.measured > 0).reverse();
                const m = sorted[p.dataIndex]?.transport_mode ?? null;
                setMode(m === mode ? null : m);
              }}
            />
          ) : (
            <Empty>No data for this day.</Empty>
          )}
        </Card>

        <Card className="wide" title="Least punctual lines" subtitle={`${selectedDay ? dayLabel(selectedDay) : ""}${mode ? `, ${MODE_LABEL[mode].toLowerCase()}` : ""} · at least 50 measured arrivals`}>
          <LineRanking rows={lines.data} />
        </Card>
      </div>

      <footer className="foot">
        <p>
          Data: <a href="https://opentransportdata.swiss">opentransportdata.swiss</a> (GTFS-RT live feed, and "Ist-Daten": every
          stop event of the previous day with planned and measured times). Punctuality follows the Swiss convention: an arrival is on
          time when it is less than 3 minutes late, counting measured times only.
        </p>
        <p>
          <a href="https://github.com/SantiagoTeranMoreno/swiss-transit-analytics">Source code on GitHub</a>
          {status.data?.last_runs.istdaten && <> · History loaded {ago(status.data.last_runs.istdaten.finished_at, now)}</>}
        </p>
      </footer>
    </div>
  );
}
