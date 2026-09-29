"""Summarise the live GTFS-RT TripUpdates feed into a national pulse and per-station state."""

from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict
from dataclasses import dataclass, field

import psycopg
from google.transit import gtfs_realtime_pb2 as rt

from .modes import uic_from_stop_id

log = logging.getLogger(__name__)

DELAYED_LIMIT_S = 180
PAST_GRACE_S = 60  # events that happened more than this before the snapshot are ignored

_SKIPPED = rt.TripUpdate.StopTimeUpdate.SKIPPED
_CANCELED = rt.TripDescriptor.CANCELED


@dataclass
class StationLive:
    upcoming_events: int = 0
    delayed_3min: int = 0
    skipped: int = 0
    delays: list[int] = field(default_factory=list)


@dataclass
class Snapshot:
    observed_at: dt.datetime
    feed_version: str | None
    trips: int = 0
    trips_cancelled: int = 0
    stop_updates: int = 0
    delays: list[int] = field(default_factory=list)
    stations: dict[int, StationLive] = field(default_factory=lambda: defaultdict(StationLive))

    @property
    def avg_delay_s(self) -> float | None:
        return round(sum(self.delays) / len(self.delays), 1) if self.delays else None

    @property
    def share_delayed(self) -> float | None:
        if not self.delays:
            return None
        return round(sum(d >= DELAYED_LIMIT_S for d in self.delays) / len(self.delays), 4)


def _delay_and_time(stu: rt.TripUpdate.StopTimeUpdate) -> tuple[int | None, int | None]:
    for ev_name in ("arrival", "departure"):
        if stu.HasField(ev_name):
            ev = getattr(stu, ev_name)
            delay = ev.delay if ev.HasField("delay") else None
            when = ev.time if ev.HasField("time") else None
            if delay is not None or when is not None:
                return delay, when
    return None, None


def summarise(payload: bytes) -> Snapshot:
    feed = rt.FeedMessage()
    feed.ParseFromString(payload)
    ts = feed.header.timestamp or int(dt.datetime.now(dt.UTC).timestamp())
    version = feed.header.feed_version if feed.header.HasField("feed_version") else None
    snap = Snapshot(dt.datetime.fromtimestamp(ts, dt.UTC), version or None)

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        snap.trips += 1
        if tu.trip.schedule_relationship == _CANCELED:
            snap.trips_cancelled += 1
            continue
        for stu in tu.stop_time_update:
            snap.stop_updates += 1
            uic = uic_from_stop_id(stu.stop_id)
            if stu.schedule_relationship == _SKIPPED:
                if uic is not None:
                    snap.stations[uic].skipped += 1
                continue
            delay, when = _delay_and_time(stu)
            if delay is None or (when is not None and when < ts - PAST_GRACE_S):
                continue
            snap.delays.append(delay)
            if uic is None:
                continue
            st = snap.stations[uic]
            st.upcoming_events += 1
            st.delays.append(delay)
            st.delayed_3min += delay >= DELAYED_LIMIT_S
    return snap


def write(conn: psycopg.Connection, snap: Snapshot) -> int:
    """Store the snapshot summary and replace the live per-station state. Does not commit."""
    conn.execute(
        "insert into transit.rt_snapshot (observed_at, feed_version, trips, trips_cancelled,"
        " stop_updates, avg_delay_s, share_delayed_3min) values (%s, %s, %s, %s, %s, %s, %s)"
        " on conflict (observed_at) do nothing",
        (
            snap.observed_at,
            snap.feed_version,
            snap.trips,
            snap.trips_cancelled,
            snap.stop_updates,
            snap.avg_delay_s,
            snap.share_delayed,
        ),
    )
    conn.execute("truncate transit.rt_station_live")
    with (
        conn.cursor() as cur,
        cur.copy(
            "copy transit.rt_station_live (uic, observed_at, upcoming_events, avg_delay_s,"
            " max_delay_s, delayed_3min, skipped) from stdin"
        ) as cp,
    ):
        for uic, st in snap.stations.items():
            avg = round(sum(st.delays) / len(st.delays), 1) if st.delays else None
            cp.write_row(
                (
                    uic,
                    snap.observed_at,
                    st.upcoming_events,
                    avg,
                    max(st.delays) if st.delays else None,
                    st.delayed_3min,
                    st.skipped,
                )
            )
    log.info(
        "gtfs-rt %s: %d trips, %d stop updates, %d stations, avg delay %ss",
        snap.observed_at.isoformat(),
        snap.trips,
        snap.stop_updates,
        len(snap.stations),
        snap.avg_delay_s,
    )
    return len(snap.stations)
