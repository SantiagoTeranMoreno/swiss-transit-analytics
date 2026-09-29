# Swiss Transit Analytics

How punctual is Swiss public transport, right now and over time? This project
collects open data from [opentransportdata.swiss](https://opentransportdata.swiss)
(SBB and every other Swiss operator: trains, trams, buses, boats and cableways)
into a PostGIS database, and serves it to a live web dashboard and a Power BI
report.

> **Status:** part 1 of 4, the data base and ingestion pipeline.
> Next: analytics API (FastAPI), live map dashboard (React + MapLibre + ECharts),
> Power BI report.

## Architecture

```mermaid
flowchart LR
    subgraph Sources["opentransportdata.swiss"]
        A["GTFS static timetable<br/>(twice a week)"]
        B["Ist-Daten: actual vs planned<br/>(one file per day, millions of rows)"]
        C["GTFS-RT trip updates<br/>(live, API key)"]
    end
    subgraph GHA["GitHub Actions"]
        D["ingest-daily<br/>06:30 UTC"]
        E["ingest-realtime<br/>every 10 min"]
    end
    A --> D
    B --> D
    C --> E
    D --> F[("PostgreSQL + PostGIS<br/>(Supabase)")]
    E --> F
    F --> G["Analytics API"]
    F --> H["Power BI"]
    G --> I["Live map dashboard"]
```

| Source | What it gives | How it is stored |
| --- | --- | --- |
| GTFS static | ~30k stops with coordinates, routes, operators | `transit.stop`, `route`, `agency`; `transit.station` view (one point per station) |
| Ist-Daten | Every stop event of the previous day, with planned and measured times | Aggregated while streaming into per-station, per-line and per-hour daily stats |
| GTFS-RT | Current delay predictions for every running trip | `rt_station_live` (current state, drives the map) and `rt_snapshot` (national time series) |

### Design decisions

- **Aggregate on ingest.** A single day of Ist-Daten has millions of rows; the
  free Supabase tier has 500 MB. The pipeline streams each file once and keeps
  only the aggregates the dashboard needs, and `sta-ingest prune` bounds the
  station-level detail (90 days by default).
- **Swiss punctuality definition.** An arrival counts as on time when it is less
  than 3 minutes late, and only *measured* times (status `REAL`) count, not
  forecasts. Cancellations are tracked separately.
- **One station key across sources.** GTFS uses numeric ids (`8503000:0:3`) or,
  since June 2026, SLOIDs (`ch:1:sloid:3000:0:3`); Ist-Daten uses the BPUIC
  number. Everything is normalised to the 7-digit station number (`uic`), so
  history and live data join onto the same map points.
- **Idempotent runs.** Every run is logged in `transit.ingestion_run`; reloading
  a day replaces its rows, and a timetable file that is already loaded is skipped.

## Data model

```
transit.stop ──(uic)── transit.station (view)
                          │
     ┌────────────────────┼──────────────────────┐
stop_day_stats      rt_station_live        v_live_map / v_stop_punctuality (views)
line_day_stats      rt_snapshot
hour_day_stats
```

See [`db/migrations/001_init.sql`](db/migrations/001_init.sql) for the full schema.

## Running it

Requirements: Python 3.11+, and PostgreSQL with PostGIS (Docker or Supabase).

```bash
docker compose up -d                       # local PostGIS on :5432
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env && set -a && . ./.env && set +a

sta-ingest migrate                         # create the schema
sta-ingest static                          # stops, routes, operators
sta-ingest istdaten --date 2026-09-28      # one day of history (default: yesterday)
sta-ingest realtime                        # live snapshot (needs OTD_API_KEY)
sta-ingest prune                           # drop old detail rows
```

Each command also takes `--file` to ingest a local download instead.

### Tests

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/transit pytest
```

Unit tests run without a database; the database tests are skipped unless
`TEST_DATABASE_URL` points at a throwaway PostGIS database (they drop and
recreate the `transit` schema).

### Deploying the scheduled ingestion

1. Create a free project on [Supabase](https://supabase.com) and copy the
   *Session pooler* connection string (Project Settings > Database).
2. Register at the [opentransportdata.swiss API Manager](https://api-manager.opentransportdata.swiss/)
   and subscribe to the GTFS-RT product to get a free API key
   (limit: 2 requests per minute).
3. In the GitHub repository, add the secrets `DATABASE_URL` and `OTD_API_KEY`
   (Settings > Secrets and variables > Actions).
4. Run *Ingest daily data* once by hand (Actions tab) to create the schema and
   load the timetable. From then on both workflows run on schedule.

GitHub pauses scheduled workflows after 60 days without repository activity;
re-enable them from the Actions tab if that happens.

## Data licence

Data © opentransportdata.swiss, published under its
[terms of use](https://opentransportdata.swiss/en/terms-of-use/). Code under the MIT licence.
