import pytest
from google.transit import gtfs_realtime_pb2 as rt

from sta_ingest import gtfs_rt, gtfs_static

NOW = 1_790_000_000


def _feed() -> bytes:
    feed = rt.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = NOW
    feed.header.feed_version = "20260925"

    def trip(tid, updates, cancelled=False):
        e = feed.entity.add(id=tid)
        e.trip_update.trip.trip_id = tid
        if cancelled:
            e.trip_update.trip.schedule_relationship = rt.TripDescriptor.CANCELED
        for stop_id, delay, when, skipped in updates:
            stu = e.trip_update.stop_time_update.add(stop_id=stop_id)
            if skipped:
                stu.schedule_relationship = rt.TripUpdate.StopTimeUpdate.SKIPPED
                continue
            stu.arrival.delay = delay
            stu.arrival.time = when

    trip(
        "t1",
        [
            ("8507000:0:5", 60, NOW - 600, False),  # already passed: ignored
            ("8503000:0:3", 240, NOW + 300, False),  # upcoming, 4 min late
        ],
    )
    trip(
        "t2",
        [
            ("ch:1:sloid:3000:0:7", 0, NOW + 900, False),
            ("ch:1:sloid:7000:1:5", 0, 0, True),  # skipped stop
        ],
    )
    trip("t3", [], cancelled=True)
    return feed.SerializeToString()


def test_summarise():
    snap = gtfs_rt.summarise(_feed())
    assert snap.feed_version == "20260925"
    assert (snap.trips, snap.trips_cancelled, snap.stop_updates) == (3, 1, 4)
    assert snap.delays == [240, 0]
    assert snap.avg_delay_s == 120.0
    assert snap.share_delayed == 0.5

    zh = snap.stations[8503000]
    assert (zh.upcoming_events, zh.delayed_3min, sorted(zh.delays)) == (2, 1, [0, 240])
    assert snap.stations[8507000].skipped == 1
    assert snap.stations[8507000].upcoming_events == 0


def test_write_live_map(conn, fixtures):
    gtfs_static.load(conn, fixtures / "gtfs_sample.zip")
    snap = gtfs_rt.summarise(_feed())
    gtfs_rt.write(conn, snap)
    gtfs_rt.write(conn, snap)  # same snapshot twice: no duplicate
    conn.commit()
    assert conn.execute("select count(*) from transit.rt_snapshot").fetchone()[0] == 1
    rows = conn.execute(
        "select uic, stop_name, avg_delay_s, max_delay_s from transit.v_live_map order by uic"
    ).fetchall()
    assert [(r[0], r[1], float(r[2]) if r[2] is not None else None, r[3]) for r in rows] == [
        (8503000, "Zürich HB", 120.0, 240),
        (8507000, "Bern", None, None),
    ]


@pytest.mark.parametrize("payload", [b""])
def test_empty_feed(payload):
    snap = gtfs_rt.summarise(payload)
    assert snap.trips == 0 and snap.avg_delay_s is None
