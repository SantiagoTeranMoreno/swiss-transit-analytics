"""Load the dimensions of the GTFS static timetable: agencies, routes and stops.

The full Swiss feed is well over 1 GB unzipped, dominated by stop_times.txt. The
dashboard only needs the dimensions, so trips and stop_times are not loaded.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from collections.abc import Iterator
from pathlib import Path

import psycopg

from .modes import mode_from_route_type, uic_from_stop_id

log = logging.getLogger(__name__)


def _rows(zf: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    with zf.open(name) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))


def _none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def parse_agencies(zf: zipfile.ZipFile) -> list[tuple]:
    return [
        (r["agency_id"], r["agency_name"], _none(r.get("agency_url")))
        for r in _rows(zf, "agency.txt")
    ]


def parse_routes(zf: zipfile.ZipFile) -> list[tuple]:
    out = []
    for r in _rows(zf, "routes.txt"):
        route_type = int(r["route_type"])
        out.append(
            (
                r["route_id"],
                _none(r.get("agency_id")),
                _none(r.get("route_short_name")),
                _none(r.get("route_long_name")),
                _none(r.get("route_desc")),
                route_type,
                mode_from_route_type(route_type),
            )
        )
    return out


def parse_stops(zf: zipfile.ZipFile) -> list[tuple]:
    out = []
    for r in _rows(zf, "stops.txt"):
        lat, lon = _none(r.get("stop_lat")), _none(r.get("stop_lon"))
        if lat is None or lon is None:
            continue
        stop_id = r["stop_id"]
        parent = _none(r.get("parent_station"))
        out.append(
            (
                stop_id,
                r["stop_name"],
                parent,
                int(r.get("location_type") or 0),
                _none(r.get("platform_code")),
                uic_from_stop_id(parent) or uic_from_stop_id(stop_id),
                float(lon),
                float(lat),
            )
        )
    return out


def feed_version(zf: zipfile.ZipFile) -> str | None:
    if "feed_info.txt" not in zf.namelist():
        return None
    for r in _rows(zf, "feed_info.txt"):
        return _none(r.get("feed_version")) or _none(r.get("feed_start_date"))
    return None


def load(conn: psycopg.Connection, zip_path: Path) -> dict[str, int]:
    """Replace agency/route/stop with the contents of a GTFS zip. Does not commit."""
    with zipfile.ZipFile(zip_path) as zf:
        agencies, routes, stops = parse_agencies(zf), parse_routes(zf), parse_stops(zf)

    conn.execute("truncate transit.agency, transit.route, transit.stop")
    with conn.cursor() as cur:
        with cur.copy("copy transit.agency (agency_id, agency_name, agency_url) from stdin") as cp:
            for row in agencies:
                cp.write_row(row)
        with cur.copy(
            "copy transit.route (route_id, agency_id, route_short_name, route_long_name,"
            " route_desc, route_type, transport_mode) from stdin"
        ) as cp:
            for row in routes:
                cp.write_row(row)
        cur.execute(
            "create temp table stop_in (stop_id text, stop_name text, parent_station text,"
            " location_type smallint, platform_code text, uic integer, lon float8, lat float8)"
        )
        with cur.copy("copy stop_in from stdin") as cp:
            for row in stops:
                cp.write_row(row)
        cur.execute(
            "insert into transit.stop (stop_id, stop_name, parent_station, location_type,"
            " platform_code, uic, geom)"
            " select stop_id, stop_name, parent_station, location_type, platform_code, uic,"
            " st_setsrid(st_makepoint(lon, lat), 4326)::geography from stop_in"
        )
        cur.execute("drop table stop_in")
    counts = {"agencies": len(agencies), "routes": len(routes), "stops": len(stops)}
    log.info("gtfs static loaded: %s", counts)
    return counts
