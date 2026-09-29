"""Command line entry point: ``sta-ingest <command>``."""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from . import db, gtfs_rt, gtfs_static, istdaten, sources
from .config import Settings

log = logging.getLogger("sta_ingest")

ZURICH = ZoneInfo("Europe/Zurich")


def cmd_migrate(settings: Settings, args: argparse.Namespace) -> None:
    with db.connect(settings.require_database_url()) as conn:
        applied = db.migrate(conn)
    log.info("migrations applied: %s", applied or "none (up to date)")


def cmd_static(settings: Settings, args: argparse.Namespace) -> None:
    http = sources.session(settings.user_agent)
    if args.file:
        path, key = Path(args.file), Path(args.file).name
    else:
        package = args.package or sources.timetable_package_id(dt.date.today())
        res = sources.latest_gtfs_static(http, package)
        path, key = None, res.name
    with db.connect(settings.require_database_url()) as conn:
        if not args.force and db.already_loaded(conn, "gtfs_static", key):
            log.info("gtfs static %s already loaded, skipping", key)
            return
        if path is None:
            path = sources.download(http, res.url)
        with db.ingestion_run(conn, "gtfs_static", key) as run:
            counts = gtfs_static.load(conn, path)
            run.rows_out = sum(counts.values())
            run.message = str(counts)


def cmd_istdaten(settings: Settings, args: argparse.Namespace) -> None:
    day = args.date or (dt.datetime.now(ZURICH).date() - dt.timedelta(days=1))
    with db.connect(settings.require_database_url()) as conn:
        key = Path(args.file).name if args.file else day.isoformat()
        if not args.force and db.already_loaded(conn, "istdaten", key):
            log.info("ist-daten %s already loaded, skipping", key)
            return
        with db.ingestion_run(conn, "istdaten", key) as run:
            if args.file:
                stats = istdaten.aggregate_file(Path(args.file))
            else:
                http = sources.session(settings.user_agent)
                res = sources.istdaten_for_day(http, day)
                log.info("streaming %s", res.url)
                with http.get(res.url, stream=True, timeout=600) as resp:
                    resp.raise_for_status()
                    resp.raw.decode_content = True
                    stats = istdaten.aggregate_stream(resp.raw)
            run.rows_in = stats.rows_in
            run.rows_out = istdaten.write(conn, stats)


def cmd_realtime(settings: Settings, args: argparse.Namespace) -> None:
    if args.file:
        payload = Path(args.file).read_bytes()
    else:
        http = sources.session(settings.user_agent)
        payload = sources.fetch_gtfs_rt(http, settings.require_api_key())
    snap = gtfs_rt.summarise(payload)
    with (
        db.connect(settings.require_database_url()) as conn,
        db.ingestion_run(conn, "gtfs_rt", snap.observed_at.isoformat()) as run,
    ):
        run.rows_in = snap.stop_updates
        run.rows_out = gtfs_rt.write(conn, snap)


def cmd_prune(settings: Settings, args: argparse.Namespace) -> None:
    """Keep the database inside a free-tier budget by dropping old detail rows."""
    with db.connect(settings.require_database_url()) as conn:
        for table, column, days in (
            ("stop_day_stats", "service_day", args.stop_days),
            ("rt_snapshot", "observed_at", args.rt_days),
            ("ingestion_run", "started_at", args.rt_days),
        ):
            sql = f"delete from transit.{table} where {column} < now() - make_interval(days => %s)"
            n = conn.execute(sql, (days,)).rowcount
            log.info("pruned %d rows from %s", n, table)
        conn.commit()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sta-ingest", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="create or upgrade the database schema").set_defaults(
        func=cmd_migrate
    )

    s = sub.add_parser("static", help="load stops/routes/agencies from the GTFS static timetable")
    s.add_argument("--file", help="local GTFS zip instead of downloading")
    s.add_argument("--package", help="CKAN dataset id (default: current timetable year)")
    s.add_argument("--force", action="store_true", help="reload even if already loaded")
    s.set_defaults(func=cmd_static)

    s = sub.add_parser("istdaten", help="aggregate one day of Ist-Daten (actual vs planned)")
    s.add_argument("--date", type=dt.date.fromisoformat, help="service day, default yesterday")
    s.add_argument("--file", help="local CSV instead of downloading")
    s.add_argument("--force", action="store_true", help="reload even if already loaded")
    s.set_defaults(func=cmd_istdaten)

    s = sub.add_parser("realtime", help="snapshot the live GTFS-RT feed")
    s.add_argument("--file", help="local protobuf file instead of calling the API")
    s.set_defaults(func=cmd_realtime)

    s = sub.add_parser("prune", help="delete old detail rows to stay within storage limits")
    s.add_argument("--stop-days", type=int, default=90)
    s.add_argument("--rt-days", type=int, default=30)
    s.set_defaults(func=cmd_prune)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args.func(Settings.from_env(), args)


if __name__ == "__main__":
    main()
