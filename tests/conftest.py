import os
from pathlib import Path

import pytest

from sta_ingest import db

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def conn():
    """A migrated database. Set TEST_DATABASE_URL to a throwaway PostGIS database."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    with db.connect(url) as c:
        c.execute("drop schema if exists transit cascade")
        c.execute("drop table if exists public.schema_migrations")
        c.commit()
        db.migrate(c)
        yield c
