from sta_ingest import cli


def test_end_to_end_with_local_files(conn, fixtures, monkeypatch):
    url = conn.info.dsn
    monkeypatch.setenv("DATABASE_URL", url)
    cli.main(["migrate"])
    cli.main(["static", "--file", str(fixtures / "gtfs_sample.zip")])
    cli.main(["static", "--file", str(fixtures / "gtfs_sample.zip")])  # skipped: already loaded
    cli.main(["istdaten", "--file", str(fixtures / "istdaten_sample.csv")])

    runs = conn.execute(
        "select source, status from transit.ingestion_run order by run_id"
    ).fetchall()
    assert runs == [("gtfs_static", "ok"), ("istdaten", "ok")]

    top = conn.execute(
        "select stop_name, punctuality from transit.v_stop_punctuality"
        " where transport_mode = 'rail' order by uic"
    ).fetchall()
    assert [(n, float(p)) for n, p in top] == [("Zürich HB", 0.5), ("Bern", 1.0)]
