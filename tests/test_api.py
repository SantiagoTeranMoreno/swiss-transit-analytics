import os

import pytest

from sta_ingest import cli, gtfs_rt

from .test_gtfs_rt import _feed

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from sta_api import cache  # noqa: E402
from sta_api.main import app  # noqa: E402


@pytest.fixture
def client(conn, fixtures, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    cli.main(["static", "--file", str(fixtures / "gtfs_sample.zip")])
    cli.main(["istdaten", "--file", str(fixtures / "istdaten_sample.csv")])
    gtfs_rt.write(conn, gtfs_rt.summarise(_feed()))
    conn.commit()
    cache.clear()
    with TestClient(app) as c:
        yield c
    cache.clear()


def test_status(client):
    body = client.get("/api/status").json()
    assert body["latest_day"] == "2026-09-28"
    assert body["days"] == ["2026-09-28"]
    assert body["live_observed_at"].startswith("2026-09-21")
    assert set(body["last_runs"]) == {"gtfs_static", "istdaten"}


def test_live(client):
    summary = client.get("/api/live/summary").json()
    assert summary["trips"] == 3
    assert summary["stations"] == 1
    assert summary["stations_with_delays"] == 1

    pulse = client.get("/api/live/pulse", params={"hours": 6}).json()
    assert len(pulse) == 1 and pulse[0]["share_delayed_3min"] == 0.5

    fc = client.get("/api/live/map").json()
    assert fc["type"] == "FeatureCollection"
    by_uic = {f["properties"]["uic"]: f for f in fc["features"]}
    assert by_uic[8503000]["properties"]["avg_delay_s"] == 120.0
    assert by_uic[8503000]["geometry"]["coordinates"] == [8.54018, 47.37818]
    assert by_uic[8507000]["properties"]["skipped"] == 1  # skipped only: still on the map


def test_history(client):
    days = client.get("/api/history/days").json()
    assert [d["service_day"] for d in days] == ["2026-09-28"]

    modes = client.get("/api/history/modes").json()
    rail = next(m for m in modes if m["transport_mode"] == "rail")
    assert rail["measured"] == 3

    hours = client.get("/api/history/hours", params={"mode": "rail"}).json()
    assert [h["hour_of_day"] for h in hours] == sorted(h["hour_of_day"] for h in hours)

    lines = client.get("/api/history/lines", params={"min_measured": 1}).json()
    assert lines[0]["line_text"]
    assert lines == sorted(lines, key=lambda r: r["punctuality"])

    stations = client.get(
        "/api/history/stations", params={"min_measured": 1, "mode": "rail"}
    ).json()
    assert [(s["name"], s["punctuality"]) for s in stations] == [
        ("Zürich HB", 0.5),
        ("Bern", 1.0),
    ]

    fc = client.get("/api/history/map", params={"day": "2026-09-28", "mode": "rail"}).json()
    assert {f["properties"]["uic"] for f in fc["features"]} == {8503000, 8507000}


def test_history_validation(client):
    assert client.get("/api/history/hours", params={"mode": "rocket"}).status_code == 422
    assert client.get("/api/history/lines", params={"day": "2020-01-01"}).json() == []


def test_stations(client):
    hits = client.get("/api/stations/search", params={"q": "zür"}).json()
    assert hits[0] == {"uic": 8503000, "name": "Zürich HB"}

    st = client.get("/api/stations/8503000").json()
    assert st["name"] == "Zürich HB"
    assert st["live"]["delayed_3min"] == 1
    assert [h["service_day"] for h in st["history"]] == ["2026-09-28"]
    assert st["modes"][0]["transport_mode"] == "rail"

    assert client.get("/api/stations/8599999").status_code == 404
