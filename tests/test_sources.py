from sta_ingest import sources


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        pass


class _Http:
    def __init__(self, body):
        self.body = body
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Resp(self.body)


def test_package_resources_multilingual_names():
    http = _Http(
        {
            "success": True,
            "result": {
                "resources": [
                    {
                        "name": {"de": "GTFS 2026-09-25", "en": "GTFS 2026-09-25 (en)"},
                        "url": "https://example.org/gtfs_fp2026_20260925.zip",
                        "created": "2026-09-25T09:00:00",
                    },
                    {
                        "name": "",
                        "url": "https://example.org/gtfs_fp2026_20260929.zip",
                        "created": "2026-09-29T09:00:00",
                    },
                    {"name": {"de": "Doku"}, "url": None},
                ]
            },
        }
    )
    res = sources.package_resources(http, "timetable-2026-gtfs2020", "k")
    assert [r.name for r in res] == ["GTFS 2026-09-25 (en)", "gtfs_fp2026_20260929.zip"]
    assert http.calls[0][1]["headers"]["Authorization"] == "Bearer k"

    latest = sources.latest_gtfs_static(http, "timetable-2026-gtfs2020", "k")
    assert latest.url.endswith("20260929.zip")


def test_istdaten_for_day_matches_url():
    import datetime as dt

    http = _Http(
        {
            "result": {
                "resources": [
                    {
                        "name": {"de": "Ist-Daten"},
                        "url": "https://example.org/2026-09-29_istdaten.csv",
                    },
                ]
            }
        }
    )
    res = sources.istdaten_for_day(http, dt.date(2026, 9, 29), "k")
    assert res.url.endswith("2026-09-29_istdaten.csv")
