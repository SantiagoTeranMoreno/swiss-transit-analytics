"""Database access: connections, migrations and ingestion run bookkeeping."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import psycopg

from .config import MIGRATIONS_DIR

log = logging.getLogger(__name__)


def connect(database_url: str) -> psycopg.Connection:
    # prepare_threshold=None keeps us compatible with PgBouncer transaction pooling
    # (the Supabase pooler), which does not support server-side prepared statements.
    return psycopg.connect(database_url, prepare_threshold=None)


def migrate(conn: psycopg.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every ``*.sql`` file in order that has not been applied yet."""
    conn.execute(
        "create table if not exists public.schema_migrations ("
        " filename text primary key, applied_at timestamptz not null default now())"
    )
    done = {r[0] for r in conn.execute("select filename from public.schema_migrations")}
    applied = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in done:
            continue
        log.info("applying migration %s", path.name)
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "insert into public.schema_migrations (filename) values (%s)", (path.name,)
            )
        applied.append(path.name)
    conn.commit()
    return applied


@dataclass
class Run:
    run_id: int
    rows_in: int = 0
    rows_out: int = 0
    message: str | None = None
    status: str = "ok"


def already_loaded(conn: psycopg.Connection, source: str, resource_key: str) -> bool:
    row = conn.execute(
        "select 1 from transit.ingestion_run"
        " where source = %s and resource_key = %s and status = 'ok' limit 1",
        (source, resource_key),
    ).fetchone()
    return row is not None


@contextmanager
def ingestion_run(conn: psycopg.Connection, source: str, resource_key: str | None) -> Iterator[Run]:
    """Record an ingestion run; the body's writes commit together with the 'ok' status."""
    run_id = conn.execute(
        "insert into transit.ingestion_run (source, resource_key) values (%s, %s) returning run_id",
        (source, resource_key),
    ).fetchone()[0]
    conn.commit()
    run = Run(run_id)
    try:
        yield run
    except BaseException as exc:
        conn.rollback()
        conn.execute(
            "update transit.ingestion_run set finished_at = now(), status = 'failed', message = %s"
            " where run_id = %s",
            (f"{type(exc).__name__}: {exc}"[:2000], run_id),
        )
        conn.commit()
        raise
    conn.execute(
        "update transit.ingestion_run set finished_at = now(), status = %s,"
        " rows_in = %s, rows_out = %s, message = %s where run_id = %s",
        (run.status, run.rows_in, run.rows_out, run.message, run_id),
    )
    conn.commit()
