from sta_ingest import gtfs_static


def test_load_and_station_view(conn, fixtures):
    counts = gtfs_static.load(conn, fixtures / "gtfs_sample.zip")
    conn.commit()
    assert counts == {"agencies": 2, "routes": 4, "stops": 5}

    modes = dict(conn.execute("select route_short_name, transport_mode from transit.route"))
    assert modes == {"IC8": "rail", "S3": "rail", "4": "tram", "31": "bus"}

    stations = dict(conn.execute("select uic, stop_name from transit.station order by uic"))
    assert stations == {8503000: "Zürich HB", 8507000: "Bern", 8591123: "Zürich Bahnhofquai/HB"}

    lon, lat = conn.execute(
        "select st_x(geom::geometry), st_y(geom::geometry) from transit.station where uic = 8507000"
    ).fetchone()
    assert (round(lon, 4), round(lat, 4)) == (7.4393, 46.9488)


def test_reload_replaces(conn, fixtures):
    gtfs_static.load(conn, fixtures / "gtfs_sample.zip")
    gtfs_static.load(conn, fixtures / "gtfs_sample.zip")
    conn.commit()
    assert conn.execute("select count(*) from transit.stop").fetchone()[0] == 5
