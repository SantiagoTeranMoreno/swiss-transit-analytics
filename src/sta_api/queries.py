"""SQL behind each endpoint. Every function takes a connection and returns plain dicts."""

from __future__ import annotations

import datetime as dt
from typing import Any

import psycopg
from psycopg.rows import dict_row

# Shared ratio expressions over summed counters (Swiss convention: on time = < 3 min late).
_RATIOS = """
    sum(events)::bigint                                                 as events,
    sum(measured)::bigint                                               as measured,
    round(sum(on_time)::numeric / nullif(sum(measured), 0), 4)          as punctuality,
    round(sum(delayed_5min)::numeric / nullif(sum(measured), 0), 4)     as share_delayed_5min,
    round(sum(cancelled)::numeric / nullif(sum(events), 0), 4)          as share_cancelled,
    round(sum(delay_sum_s)::numeric / nullif(sum(measured), 0), 1)      as avg_delay_s
"""


def _all(conn: psycopg.Connection, sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params or {}).fetchall()


def _one(conn: psycopg.Connection, sql: str, params: dict[str, Any] | None = None) -> dict | None:
    rows = _all(conn, sql, params)
    return rows[0] if rows else None


def _feature(row: dict, lon: float, lat: float) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": row,
    }


def _collection(rows: list[dict]) -> dict:
    features = [_feature(r, r.pop("lon"), r.pop("lat")) for r in rows]
    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def status(conn: psycopg.Connection) -> dict:
    days = [
        r["service_day"]
        for r in _all(
            conn,
            "select distinct service_day from transit.hour_day_stats order by service_day desc",
        )
    ]
    runs = _all(
        conn,
        "select distinct on (source) source, finished_at, resource_key"
        " from transit.ingestion_run where status = 'ok'"
        " order by source, finished_at desc",
    )
    live = _one(conn, "select max(observed_at) as observed_at from transit.rt_snapshot")
    return {
        "days": days,
        "latest_day": days[0] if days else None,
        "live_observed_at": live["observed_at"] if live else None,
        "last_runs": {r["source"]: r for r in runs},
    }


def latest_day(conn: psycopg.Connection) -> dt.date | None:
    row = _one(conn, "select max(service_day) as d from transit.hour_day_stats")
    return row["d"] if row else None


# ---------------------------------------------------------------------------
# Live (GTFS-RT)
# ---------------------------------------------------------------------------


def live_summary(conn: psycopg.Connection) -> dict | None:
    snap = _one(
        conn,
        "select observed_at, trips, trips_cancelled, stop_updates, avg_delay_s,"
        " share_delayed_3min from transit.rt_snapshot order by observed_at desc limit 1",
    )
    if snap is None:
        return None
    counts = _one(
        conn,
        "select count(*) as stations, count(*) filter (where delayed_3min > 0)"
        " as stations_with_delays from transit.rt_station_live where upcoming_events > 0",
    )
    return snap | counts


def live_pulse(conn: psycopg.Connection, hours: int) -> list[dict]:
    return _all(
        conn,
        "select observed_at, trips, trips_cancelled, avg_delay_s, share_delayed_3min"
        " from transit.rt_snapshot"
        " where observed_at >= (select max(observed_at) from transit.rt_snapshot)"
        "   - make_interval(hours => %(hours)s)"
        " order by observed_at",
        {"hours": hours},
    )


def live_map(conn: psycopg.Connection) -> dict:
    rows = _all(
        conn,
        "select uic, stop_name as name, upcoming_events, avg_delay_s, max_delay_s,"
        " delayed_3min, skipped,"
        " round(st_x(geom::geometry)::numeric, 5)::float as lon,"
        " round(st_y(geom::geometry)::numeric, 5)::float as lat"
        " from transit.v_live_map where upcoming_events > 0 or skipped > 0"
        " order by avg_delay_s nulls first",  # most delayed drawn last, on top
    )
    return _collection(rows)


# ---------------------------------------------------------------------------
# History (Ist-Daten aggregates)
# ---------------------------------------------------------------------------


def history_days(conn: psycopg.Connection, mode: str | None, limit: int) -> list[dict]:
    return _all(
        conn,
        f"select service_day, {_RATIOS} from transit.hour_day_stats"
        " where %(mode)s::text is null or transport_mode = %(mode)s"
        " group by service_day order by service_day desc limit %(limit)s",
        {"mode": mode, "limit": limit},
    )[::-1]


def history_modes(conn: psycopg.Connection, day: dt.date) -> list[dict]:
    return _all(
        conn,
        f"select transport_mode, {_RATIOS} from transit.hour_day_stats"
        " where service_day = %(day)s group by transport_mode order by sum(events) desc",
        {"day": day},
    )


def history_hours(conn: psycopg.Connection, day: dt.date, mode: str | None) -> list[dict]:
    return _all(
        conn,
        f"select hour_of_day, {_RATIOS} from transit.hour_day_stats"
        " where service_day = %(day)s and (%(mode)s::text is null or transport_mode = %(mode)s)"
        " group by hour_of_day order by hour_of_day",
        {"day": day, "mode": mode},
    )


def _ranking_order(order: str) -> str:
    # Worst first: lowest punctuality, then highest average delay as a tie-breaker.
    if order == "best":
        return "punctuality desc nulls last, avg_delay_s asc"
    return "punctuality asc nulls last, avg_delay_s desc"


def history_lines(
    conn: psycopg.Connection,
    day: dt.date,
    mode: str | None,
    order: str,
    limit: int,
    min_measured: int,
) -> list[dict]:
    return _all(
        conn,
        f"select operator_abbr, line_text, transport_mode, sum(trips)::bigint as trips,"
        f" max(delay_max_s) as delay_max_s, {_RATIOS}"
        " from transit.line_day_stats"
        " where service_day = %(day)s and (%(mode)s::text is null or transport_mode = %(mode)s)"
        " group by operator_abbr, line_text, transport_mode"
        " having sum(measured) >= %(min)s"
        f" order by {_ranking_order(order)} limit %(limit)s",
        {"day": day, "mode": mode, "min": min_measured, "limit": limit},
    )


def history_stations(
    conn: psycopg.Connection,
    day: dt.date,
    mode: str | None,
    order: str,
    limit: int,
    min_measured: int,
) -> list[dict]:
    return _all(
        conn,
        "with agg as ("
        f"  select uic, max(delay_max_s) as delay_max_s, {_RATIOS}"
        "   from transit.stop_day_stats"
        "   where service_day = %(day)s and (%(mode)s::text is null or transport_mode = %(mode)s)"
        "   group by uic having sum(measured) >= %(min)s"
        ")"
        " select agg.*, st.stop_name as name from agg"
        " left join transit.station st on st.uic = agg.uic"
        f" order by {_ranking_order(order)} limit %(limit)s",
        {"day": day, "mode": mode, "min": min_measured, "limit": limit},
    )


def history_map(conn: psycopg.Connection, day: dt.date, mode: str | None) -> dict:
    rows = _all(
        conn,
        "with agg as ("
        f"  select uic, {_RATIOS} from transit.stop_day_stats"
        "   where service_day = %(day)s and (%(mode)s::text is null or transport_mode = %(mode)s)"
        "   group by uic having sum(measured) > 0"
        ")"
        " select agg.uic, st.stop_name as name, agg.measured, agg.punctuality, agg.avg_delay_s,"
        " round(st_x(st.geom::geometry)::numeric, 5)::float as lon,"
        " round(st_y(st.geom::geometry)::numeric, 5)::float as lat"
        " from agg join transit.station st on st.uic = agg.uic"
        " order by agg.punctuality desc",  # least punctual drawn last, on top
        {"day": day, "mode": mode},
    )
    return _collection(rows)


# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------


def station_search(conn: psycopg.Connection, q: str, limit: int) -> list[dict]:
    return _all(
        conn,
        "select uic, stop_name as name from transit.station"
        " where stop_name ilike %(pattern)s"
        " order by (stop_name ilike %(prefix)s) desc, length(stop_name), stop_name"
        " limit %(limit)s",
        {"pattern": f"%{q}%", "prefix": f"{q}%", "limit": limit},
    )


def station_detail(conn: psycopg.Connection, uic: int, days: int) -> dict | None:
    st = _one(
        conn,
        "select uic, stop_name as name,"
        " round(st_x(geom::geometry)::numeric, 5)::float as lon,"
        " round(st_y(geom::geometry)::numeric, 5)::float as lat"
        " from transit.station where uic = %(uic)s",
        {"uic": uic},
    )
    if st is None:
        return None
    st["live"] = _one(
        conn,
        "select observed_at, upcoming_events, avg_delay_s, max_delay_s, delayed_3min, skipped"
        " from transit.rt_station_live where uic = %(uic)s",
        {"uic": uic},
    )
    st["history"] = _all(
        conn,
        f"select service_day, {_RATIOS} from transit.stop_day_stats where uic = %(uic)s"
        " group by service_day order by service_day desc limit %(days)s",
        {"uic": uic, "days": days},
    )[::-1]
    st["modes"] = _all(
        conn,
        f"select transport_mode, {_RATIOS} from transit.stop_day_stats"
        " where uic = %(uic)s and service_day = ("
        "   select max(service_day) from transit.stop_day_stats where uic = %(uic)s)"
        " group by transport_mode order by sum(events) desc",
        {"uic": uic},
    )
    return st
