import { delay, int, MODE_LABEL, pct } from "../format";
import { dayStatus, STATUS } from "../theme";
import type { LineRow, StationRow } from "../types";
import { Empty } from "./ui";

function Bar({ value }: { value: number | null }) {
  return (
    <span className="rank-bar" aria-hidden>
      <span style={{ width: `${(value ?? 0) * 100}%`, background: STATUS[dayStatus(value)] }} />
    </span>
  );
}

export function LineRanking({ rows }: { rows: LineRow[] | undefined }) {
  if (rows && !rows.length) return <Empty>No line has enough measured arrivals for this filter.</Empty>;
  return (
    <table className="rank">
      <thead>
        <tr>
          <th>Line</th>
          <th className="num">On time</th>
          <th className="num hide-sm">Avg delay</th>
          <th className="num hide-sm">Trips</th>
        </tr>
      </thead>
      <tbody>
        {rows?.map((r) => (
          <tr key={`${r.operator_abbr}|${r.line_text}|${r.transport_mode}`}>
            <td>
              <span className="line-badge">{r.line_text}</span>
              <span className="muted">
                {r.operator_abbr} · {MODE_LABEL[r.transport_mode]}
              </span>
            </td>
            <td className="num">
              <Bar value={r.punctuality} />
              {pct(r.punctuality)}
            </td>
            <td className="num hide-sm">{delay(r.avg_delay_s)}</td>
            <td className="num hide-sm">{int(r.trips)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function StationRanking({
  rows,
  onSelect,
}: {
  rows: StationRow[] | undefined;
  onSelect: (uic: number) => void;
}) {
  if (rows && !rows.length) return <Empty>No station has enough measured arrivals for this filter.</Empty>;
  return (
    <table className="rank clickable">
      <thead>
        <tr>
          <th>Station</th>
          <th className="num">On time</th>
          <th className="num hide-sm">Arrivals</th>
        </tr>
      </thead>
      <tbody>
        {rows?.map((r) => (
          <tr key={r.uic} onClick={() => onSelect(r.uic)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onSelect(r.uic)}>
            <td>{r.name ?? r.uic}</td>
            <td className="num">
              <Bar value={r.punctuality} />
              {pct(r.punctuality)}
            </td>
            <td className="num hide-sm">{int(r.measured)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
