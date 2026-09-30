"""FastAPI application: ``uvicorn sta_api.main:app``."""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse
from psycopg.types.numeric import FloatLoader
from psycopg_pool import ConnectionPool

from sta_ingest.modes import MODES

from . import queries
from .cache import cached

Mode = Literal[MODES]  # type: ignore[valid-type]
Order = Literal["worst", "best"]

LIVE_TTL_S = 30
HISTORY_TTL_S = 600


def _configure(conn: psycopg.Connection) -> None:
    # Ratios and averages are numeric in SQL; JSON clients want numbers, not Decimal strings.
    conn.adapters.register_loader("numeric", FloatLoader)


@asynccontextmanager
async def lifespan(app: FastAPI):
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    # Small pool: the Supabase free tier allows few connections, and responses are cached.
    # prepare_threshold=None keeps the PgBouncer-based pooler happy.
    pool = ConnectionPool(
        url,
        min_size=1,
        max_size=int(os.environ.get("STA_DB_POOL_SIZE", "4")),
        kwargs={"prepare_threshold": None, "autocommit": True},
        configure=_configure,
        check=ConnectionPool.check_connection,
        open=False,
    )
    pool.open()
    app.state.pool = pool
    yield
    pool.close()


app = FastAPI(
    title="Swiss Transit Analytics API",
    version="0.1.0",
    description=(
        "Punctuality of Swiss public transport, live (GTFS-RT) and historical (Ist-Daten). "
        "Data: opentransportdata.swiss."
    ),
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("STA_CORS_ORIGINS", "*").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_conn(request: Request) -> Iterator[psycopg.Connection]:
    with request.app.state.pool.connection() as conn:
        yield conn


Conn = Annotated[psycopg.Connection, Depends(get_conn)]


def _day_or_latest(conn: psycopg.Connection, day: dt.date | None) -> dt.date:
    day = day or cached(("latest_day",), HISTORY_TTL_S, lambda: queries.latest_day(conn))
    if day is None:
        raise HTTPException(404, "no historical data loaded yet")
    return day


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/api/health")
def health(conn: Conn) -> dict:
    conn.execute("select 1")
    return {"status": "ok"}


@app.get("/api/status")
def status(conn: Conn) -> dict:
    """Available service days and when each source was last refreshed."""
    return cached(("status",), LIVE_TTL_S, lambda: queries.status(conn))


# ---------------------------------------------------------------------------
# Live
# ---------------------------------------------------------------------------


@app.get("/api/live/summary")
def live_summary(conn: Conn) -> dict | None:
    """National state from the latest GTFS-RT snapshot."""
    return cached(("live_summary",), LIVE_TTL_S, lambda: queries.live_summary(conn))


@app.get("/api/live/pulse")
def live_pulse(conn: Conn, hours: Annotated[int, Query(ge=1, le=24 * 30)] = 24) -> list[dict]:
    """National delay over time, one point per snapshot."""
    return cached(("live_pulse", hours), LIVE_TTL_S, lambda: queries.live_pulse(conn, hours))


@app.get("/api/live/map")
def live_map(conn: Conn) -> dict:
    """GeoJSON: every station with upcoming events and its current delay."""
    return cached(("live_map",), LIVE_TTL_S, lambda: queries.live_map(conn))


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@app.get("/api/history/days")
def history_days(
    conn: Conn,
    mode: Mode | None = None,
    limit: Annotated[int, Query(ge=1, le=366)] = 90,
) -> list[dict]:
    """National punctuality per service day, oldest first."""
    return cached(
        ("days", mode, limit), HISTORY_TTL_S, lambda: queries.history_days(conn, mode, limit)
    )


@app.get("/api/history/modes")
def history_modes(conn: Conn, day: dt.date | None = None) -> list[dict]:
    """Punctuality per transport mode for one day (default: latest)."""
    d = _day_or_latest(conn, day)
    return cached(("modes", d), HISTORY_TTL_S, lambda: queries.history_modes(conn, d))


@app.get("/api/history/hours")
def history_hours(conn: Conn, day: dt.date | None = None, mode: Mode | None = None) -> list[dict]:
    """Punctuality per hour of the day."""
    d = _day_or_latest(conn, day)
    return cached(("hours", d, mode), HISTORY_TTL_S, lambda: queries.history_hours(conn, d, mode))


@app.get("/api/history/lines")
def history_lines(
    conn: Conn,
    day: dt.date | None = None,
    mode: Mode | None = None,
    order: Order = "worst",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    min_measured: Annotated[int, Query(ge=1)] = 50,
) -> list[dict]:
    """Lines ranked by punctuality; lines with few measured events are left out."""
    d = _day_or_latest(conn, day)
    return cached(
        ("lines", d, mode, order, limit, min_measured),
        HISTORY_TTL_S,
        lambda: queries.history_lines(conn, d, mode, order, limit, min_measured),
    )


@app.get("/api/history/stations")
def history_stations(
    conn: Conn,
    day: dt.date | None = None,
    mode: Mode | None = None,
    order: Order = "worst",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    min_measured: Annotated[int, Query(ge=1)] = 50,
) -> list[dict]:
    """Stations ranked by punctuality."""
    d = _day_or_latest(conn, day)
    return cached(
        ("stations", d, mode, order, limit, min_measured),
        HISTORY_TTL_S,
        lambda: queries.history_stations(conn, d, mode, order, limit, min_measured),
    )


@app.get("/api/history/map")
def history_map(conn: Conn, day: dt.date | None = None, mode: Mode | None = None) -> dict:
    """GeoJSON: punctuality of every station on one day."""
    d = _day_or_latest(conn, day)
    return cached(("map", d, mode), HISTORY_TTL_S, lambda: queries.history_map(conn, d, mode))


# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------


@app.get("/api/stations/search")
def station_search(
    conn: Conn,
    q: Annotated[str, Query(min_length=2, max_length=60)],
    limit: Annotated[int, Query(ge=1, le=25)] = 8,
) -> list[dict]:
    return cached(
        ("search", q.lower(), limit),
        HISTORY_TTL_S,
        lambda: queries.station_search(conn, q, limit),
    )


@app.get("/api/stations/{uic}")
def station_detail(conn: Conn, uic: int, days: Annotated[int, Query(ge=1, le=366)] = 30) -> dict:
    """One station: location, live state, daily punctuality and today's mode split."""
    st = cached(("station", uic, days), LIVE_TTL_S, lambda: queries.station_detail(conn, uic, days))
    if st is None:
        raise HTTPException(404, "station not found")
    return st
