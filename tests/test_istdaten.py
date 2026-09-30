import datetime as dt

from sta_ingest import istdaten


def test_aggregate_sample(fixtures):
    stats = istdaten.aggregate_file(fixtures / "istdaten_sample.csv")

    assert stats.service_day == dt.date(2026, 9, 28)
    assert stats.rows_in == 7

    zh = stats.by_stop[(8503000, "rail")]
    assert (zh.events, zh.measured, zh.on_time, zh.delayed_5min, zh.cancelled) == (4, 2, 1, 1, 1)
    assert (zh.delay_sum_s, zh.delay_max_s) == (310 + 90, 310)

    bern = stats.by_stop[(8507000, "rail")]
    assert (bern.events, bern.measured, bern.on_time, bern.delay_sum_s) == (1, 1, 1, 40)

    tram = stats.by_stop[(8591123, "tram")]
    assert (tram.measured, tram.on_time, tram.delay_sum_s) == (1, 1, 0)  # early arrival

    assert (8502204, "rail") not in stats.by_stop  # pass-through ignored

    ic8 = stats.by_line[("SBB", "IC8", "rail")]
    assert (ic8.events, len(ic8.trips)) == (5, 4)

    assert stats.by_hour[(7, "rail")].events == 2
    assert stats.by_hour[(7, "tram")].events == 1


def test_parse_ts():
    assert istdaten.parse_ts("28.09.2026 07:58") == dt.datetime(2026, 9, 28, 7, 58)
    assert istdaten.parse_ts("28.09.2026 08:03:10") == dt.datetime(2026, 9, 28, 8, 3, 10)
    assert istdaten.parse_ts("") is None
    assert istdaten.parse_ts("garbage") is None


def test_write(conn, fixtures):
    stats = istdaten.aggregate_file(fixtures / "istdaten_sample.csv")
    istdaten.write(conn, stats)
    istdaten.write(conn, stats)  # idempotent per service day
    conn.commit()
    row = conn.execute(
        "select events, measured, on_time, cancelled from transit.stop_day_stats"
        " where uic = 8503000"
    ).fetchone()
    assert row == (4, 2, 1, 1)
    assert conn.execute("select count(*) from transit.line_day_stats").fetchone()[0] == 2


def test_migration_merges_suffixed_station_numbers(conn):
    from sta_ingest import db

    conn.execute("delete from public.schema_migrations where filename like '002_%'")
    rows = [(8593617, 10, 8, 6, 100, 200), (859361701, 5, 4, 1, 400, 900)]
    for uic, events, measured, on_time, delay_sum, delay_max in rows:
        conn.execute(
            "insert into transit.stop_day_stats values"
            " ('2026-09-29', %s, 'bus', %s, %s, %s, 0, 0, 0, %s, %s)",
            (uic, events, measured, on_time, delay_sum, delay_max),
        )
    conn.commit()
    db.migrate(conn)
    got = conn.execute(
        "select uic, events, measured, on_time, delay_sum_s, delay_max_s"
        " from transit.stop_day_stats"
    ).fetchall()
    assert got == [(8593617, 15, 12, 7, 500, 900)]
