import { useMemo } from "react";
import { stationDaysOption } from "../charts";
import { ago, delay, int, MODE_LABEL, pct } from "../format";
import { chartTheme, dayStatus, liveStatus, LIVE_BINS } from "../theme";
import type { StationDetail } from "../types";
import { Chart } from "./Chart";
import { Empty, Stat, StatusDot } from "./ui";

export function StationPanel({
  station,
  now,
  dark,
  onClose,
}: {
  station: StationDetail;
  now: number;
  dark: boolean;
  onClose: () => void;
}) {
  const option = useMemo(
    () => stationDaysOption(station.history, chartTheme()),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [station, dark],
  );
  const live = station.live;
  const latest = station.history.at(-1);
  const liveKey = liveStatus(live?.avg_delay_s);

  return (
    <div className="station">
      <div className="station-head">
        <h2>{station.name}</h2>
        <button className="ghost" onClick={onClose} aria-label="Close station">
          ✕
        </button>
      </div>

      <h3>Right now</h3>
      {live ? (
        <>
          <div className="stats-2">
            <Stat label="Average delay" value={delay(live.avg_delay_s)} />
            <Stat label="Upcoming stops ≥ 3 min late" value={`${int(live.delayed_3min)} / ${int(live.upcoming_events)}`} />
          </div>
          <p className="muted small">
            {liveKey !== "none" && (
              <StatusDot status={liveKey} label={LIVE_BINS.find((b) => b.key === liveKey)!.label} />
            )}{" "}
            Predicted by the live feed {ago(live.observed_at, now)}
            {live.skipped ? ` · ${int(live.skipped)} stops skipped` : ""}
          </p>
        </>
      ) : (
        <Empty>No trips at this station in the latest live snapshot.</Empty>
      )}

      <h3>Measured history</h3>
      {latest ? (
        <>
          <div className="stats-2">
            <Stat
              label="On time, last day"
              value={pct(latest.punctuality)}
              note={<StatusDot status={dayStatus(latest.punctuality)} label={`${int(latest.measured)} arrivals`} />}
            />
            <Stat label="Average delay" value={delay(latest.avg_delay_s)} />
          </div>
          {station.history.length > 1 && (
            <Chart option={option} height={140} label={`Daily punctuality at ${station.name}`} />
          )}
          {station.modes.length > 1 && (
            <table className="rank compact">
              <tbody>
                {station.modes.map((m) => (
                  <tr key={m.transport_mode}>
                    <td>{MODE_LABEL[m.transport_mode]}</td>
                    <td className="num">{pct(m.punctuality)}</td>
                    <td className="num muted">{int(m.measured)} arrivals</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : (
        <Empty>No measured arrivals recorded here yet.</Empty>
      )}
    </div>
  );
}
