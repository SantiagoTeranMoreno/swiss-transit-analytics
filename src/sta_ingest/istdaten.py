"""Aggregate a daily Ist-Daten file (actual vs planned times) into punctuality stats.

A daily file has millions of rows (one per stop event), far too much to keep
raw on a free database tier. It is streamed once and reduced to three tables:
per station, per line and per hour of day.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

import psycopg

from .modes import mode_from_product, uic_from_bpuic

log = logging.getLogger(__name__)

ON_TIME_LIMIT_S = 180  # Swiss convention: less than 3 minutes late counts as punctual
DELAYED_LIMIT_S = 300


@dataclass
class Counter:
    events: int = 0
    measured: int = 0
    on_time: int = 0
    delayed_5min: int = 0
    cancelled: int = 0
    extra_trips: int = 0
    delay_sum_s: int = 0
    delay_max_s: int = 0
    trips: set[str] = field(default_factory=set)

    def add(self, delay_s: int | None, cancelled: bool, extra: bool, trip: str | None) -> None:
        self.events += 1
        self.cancelled += cancelled
        self.extra_trips += extra
        if trip:
            self.trips.add(trip)
        if delay_s is None:
            return
        self.measured += 1
        self.on_time += delay_s < ON_TIME_LIMIT_S
        self.delayed_5min += delay_s >= DELAYED_LIMIT_S
        if delay_s > 0:
            self.delay_sum_s += delay_s
            self.delay_max_s = max(self.delay_max_s, delay_s)


@dataclass
class DayStats:
    service_day: dt.date | None = None
    rows_in: int = 0
    by_stop: dict[tuple[int, str], Counter] = field(default_factory=lambda: defaultdict(Counter))
    by_line: dict[tuple[str, str, str], Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    by_hour: dict[tuple[int, str], Counter] = field(default_factory=lambda: defaultdict(Counter))


def parse_ts(value: str | None) -> dt.datetime | None:
    """Parse ``DD.MM.YYYY HH:MM[:SS]`` (the Ist-Daten format)."""
    v = (value or "").strip()
    if not v:
        return None
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return dt.datetime.strptime(v, fmt)
        except ValueError:
            pass
    return None


def parse_day(value: str | None) -> dt.date | None:
    v = (value or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"true", "1", "t", "ja"}


def _event(row: dict[str, str]) -> tuple[dt.datetime | None, int | None]:
    """Planned time of the event and its measured delay (None when not measured).

    Arrival is used when present; the first stop of a trip only has a departure.
    """
    for planned_col, actual_col, status_col in (
        ("ANKUNFTSZEIT", "AN_PROGNOSE", "AN_PROGNOSE_STATUS"),
        ("ABFAHRTSZEIT", "AB_PROGNOSE", "AB_PROGNOSE_STATUS"),
    ):
        planned = parse_ts(row.get(planned_col))
        if planned is None:
            continue
        actual = parse_ts(row.get(actual_col))
        status = (row.get(status_col) or "").strip().upper()
        if actual is None or status != "REAL":
            return planned, None
        return planned, int((actual - planned).total_seconds())
    return None, None


def reader(fh: IO[str]) -> Iterator[dict[str, str]]:
    """CSV reader that detects the separator (the files use ';')."""
    header = fh.readline()
    delimiter = ";" if header.count(";") >= header.count(",") else ","
    fieldnames = [h.strip().strip('"').lstrip("﻿") for h in header.rstrip("\r\n").split(delimiter)]
    yield from csv.DictReader(fh, fieldnames=fieldnames, delimiter=delimiter)


def aggregate(rows: Iterable[dict[str, str]]) -> DayStats:
    stats = DayStats()
    for row in rows:
        stats.rows_in += 1
        if _flag(row.get("DURCHFAHRT_TF")):
            continue
        uic = uic_from_bpuic(row.get("BPUIC"), row.get("SLOID"))
        planned, delay = _event(row)
        if uic is None or planned is None:
            continue
        if stats.service_day is None:
            stats.service_day = parse_day(row.get("BETRIEBSTAG"))
        mode = mode_from_product(row.get("PRODUKT_ID"))
        cancelled = _flag(row.get("FAELLT_AUS_TF"))
        extra = _flag(row.get("ZUSATZFAHRT_TF"))
        if cancelled:
            delay = None
        operator = (row.get("BETREIBER_ABK") or "").strip() or "?"
        line = (row.get("LINIEN_TEXT") or "").strip() or "?"
        trip = (row.get("FAHRT_BEZEICHNER") or "").strip() or None

        stats.by_stop[(uic, mode)].add(delay, cancelled, extra, None)
        stats.by_line[(operator, line, mode)].add(delay, cancelled, extra, trip)
        stats.by_hour[(planned.hour, mode)].add(delay, cancelled, extra, None)
    return stats


def aggregate_file(path: Path) -> DayStats:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return aggregate(reader(fh))


def aggregate_stream(raw: IO[bytes]) -> DayStats:
    return aggregate(reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")))


def write(conn: psycopg.Connection, stats: DayStats) -> int:
    """Replace the stats for the service day. Does not commit."""
    day = stats.service_day
    if day is None:
        raise ValueError("no usable rows: service day unknown")
    for table in ("stop_day_stats", "line_day_stats", "hour_day_stats"):
        conn.execute(f"delete from transit.{table} where service_day = %s", (day,))

    with conn.cursor() as cur:
        with cur.copy(
            "copy transit.stop_day_stats (service_day, uic, transport_mode, events, measured,"
            " on_time, delayed_5min, cancelled, extra_trips, delay_sum_s, delay_max_s) from stdin"
        ) as cp:
            for (uic, mode), c in stats.by_stop.items():
                cp.write_row(
                    (
                        day,
                        uic,
                        mode,
                        c.events,
                        c.measured,
                        c.on_time,
                        c.delayed_5min,
                        c.cancelled,
                        c.extra_trips,
                        c.delay_sum_s,
                        c.delay_max_s,
                    )
                )
        with cur.copy(
            "copy transit.line_day_stats (service_day, operator_abbr, line_text, transport_mode,"
            " events, measured, on_time, delayed_5min, cancelled, trips, delay_sum_s, delay_max_s)"
            " from stdin"
        ) as cp:
            for (op, line, mode), c in stats.by_line.items():
                cp.write_row(
                    (
                        day,
                        op,
                        line,
                        mode,
                        c.events,
                        c.measured,
                        c.on_time,
                        c.delayed_5min,
                        c.cancelled,
                        len(c.trips),
                        c.delay_sum_s,
                        c.delay_max_s,
                    )
                )
        with cur.copy(
            "copy transit.hour_day_stats (service_day, hour_of_day, transport_mode, events,"
            " measured, on_time, delayed_5min, cancelled, delay_sum_s) from stdin"
        ) as cp:
            for (hour, mode), c in stats.by_hour.items():
                cp.write_row(
                    (
                        day,
                        hour,
                        mode,
                        c.events,
                        c.measured,
                        c.on_time,
                        c.delayed_5min,
                        c.cancelled,
                        c.delay_sum_s,
                    )
                )
    rows_out = len(stats.by_stop) + len(stats.by_line) + len(stats.by_hour)
    log.info("ist-daten %s: %d rows in, %d aggregate rows out", day, stats.rows_in, rows_out)
    return rows_out
