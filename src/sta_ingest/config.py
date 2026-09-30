"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# The CKAN catalogue API sits behind the API Manager and needs a key.
CKAN_BASE_URL = "https://api.opentransportdata.swiss/ckan-api"
GTFS_RT_URL = "https://api.opentransportdata.swiss/la/gtfs-rt"
ISTDATEN_PACKAGE_ID = "ist-daten-v2"

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"

DEFAULT_USER_AGENT = "swiss-transit-analytics/0.1"


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    api_key: str | None
    ckan_api_key: str | None
    user_agent: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get("DATABASE_URL") or None,
            api_key=os.environ.get("OTD_API_KEY") or None,
            # A separate key only matters if the CKAN API product was subscribed apart.
            ckan_api_key=os.environ.get("OTD_CKAN_API_KEY")
            or os.environ.get("OTD_API_KEY")
            or None,
            user_agent=os.environ.get("STA_USER_AGENT") or DEFAULT_USER_AGENT,
        )

    def require_database_url(self) -> str:
        if not self.database_url:
            raise SystemExit("DATABASE_URL is not set (see .env.example)")
        return self.database_url

    def require_api_key(self) -> str:
        if not self.api_key:
            raise SystemExit(
                "OTD_API_KEY is not set: request a free key at "
                "https://api-manager.opentransportdata.swiss/"
            )
        return self.api_key

    def require_ckan_api_key(self) -> str:
        if not self.ckan_api_key:
            raise SystemExit(
                "OTD_API_KEY (or OTD_CKAN_API_KEY) is not set: the CKAN catalogue API needs a key "
                "from https://api-manager.opentransportdata.swiss/"
            )
        return self.ckan_api_key
