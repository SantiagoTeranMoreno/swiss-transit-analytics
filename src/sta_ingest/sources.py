"""Locating and downloading files from opentransportdata.swiss (CKAN catalogue + API)."""

from __future__ import annotations

import datetime as dt
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import CKAN_BASE_URL, GTFS_RT_URL, ISTDATEN_PACKAGE_ID

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Resource:
    name: str
    url: str
    created: str


def session(user_agent: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent, "Accept-Encoding": "br, gzip, deflate"})
    return s


def _check(resp: requests.Response, what: str) -> None:
    if resp.status_code in (401, 403):
        raise PermissionError(
            f"{what}: HTTP {resp.status_code}. Check that the API key is valid and subscribed "
            f"to this API in the API Manager. Response: {resp.text[:300]!r}"
        )
    resp.raise_for_status()


def package_resources(http: requests.Session, package_id: str, api_key: str) -> list[Resource]:
    resp = http.get(
        f"{CKAN_BASE_URL}/package_show",
        params={"id": package_id},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    _check(resp, f"CKAN package_show {package_id}")
    body = resp.json()
    if body.get("success") is False:
        raise RuntimeError(f"CKAN package_show failed for {package_id}: {body.get('error')}")
    result = body.get("result", body)
    return [
        Resource(
            name=_text(r.get("name")) or r["url"].rsplit("/", 1)[-1],
            url=r["url"],
            created=_text(r.get("created")),
        )
        for r in result.get("resources", [])
        if isinstance(r.get("url"), str) and r["url"]
    ]


def _text(value: object) -> str:
    """CKAN fields may be plain strings or multilingual dicts like {"de": ..., "en": ...}."""
    if isinstance(value, dict):
        for lang in ("en", "de", "fr", "it"):
            if value.get(lang):
                return str(value[lang])
        return next((str(v) for v in value.values() if v), "")
    return str(value) if value else ""


def timetable_package_id(today: dt.date) -> str:
    """The Swiss timetable year switches in mid-December; its GTFS dataset is named by year."""
    year = today.year + 1 if (today.month == 12 and today.day >= 14) else today.year
    return f"timetable-{year}-gtfs2020"


def latest_gtfs_static(http: requests.Session, package_id: str, api_key: str) -> Resource:
    resources = package_resources(http, package_id, api_key)
    zips = [r for r in resources if r.url.lower().split("?", 1)[0].endswith(".zip")]
    if not zips:
        raise RuntimeError(f"no GTFS zip found in dataset {package_id}")
    return max(zips, key=lambda r: (r.created, r.name))


def istdaten_for_day(http: requests.Session, day: dt.date, api_key: str) -> Resource:
    """Find the daily Ist-Daten CSV for a service day (named like ``2026-09-28_istdaten.csv``)."""
    stamp = day.isoformat()
    for r in package_resources(http, ISTDATEN_PACKAGE_ID, api_key):
        if stamp in r.name or stamp in r.url:
            return r
    raise LookupError(f"no Ist-Daten file for {stamp} in dataset {ISTDATEN_PACKAGE_ID} (yet)")


def download(http: requests.Session, url: str, dest_dir: Path | None = None) -> Path:
    dest_dir = dest_dir or Path(tempfile.mkdtemp(prefix="sta-"))
    dest = dest_dir / (url.rsplit("/", 1)[-1].split("?", 1)[0] or "download")
    log.info("downloading %s", url)
    with http.get(url, stream=True, timeout=300) as resp:
        _check(resp, f"download {url}")
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    log.info("saved %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
    return dest


def fetch_gtfs_rt(http: requests.Session, api_key: str) -> bytes:
    """Fetch the national GTFS-RT TripUpdates feed (protobuf). Limit: 2 requests/minute."""
    resp = http.get(
        GTFS_RT_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
        allow_redirects=True,
    )
    _check(resp, "GTFS-RT")
    ctype = resp.headers.get("Content-Type", "")
    if "json" in ctype or "html" in ctype or resp.content[:1] in (b"{", b"<"):
        raise RuntimeError(
            f"GTFS-RT returned {ctype or 'text'} instead of protobuf: {resp.text[:300]!r}"
        )
    return resp.content
