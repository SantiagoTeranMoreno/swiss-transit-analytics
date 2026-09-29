-- Swiss Transit Analytics: core schema.
-- Target: PostgreSQL 15+ with PostGIS (Supabase free tier works).
--
-- Storage budget matters (Supabase free tier = 500 MB), so raw feeds are never
-- stored row-for-row. The static timetable keeps only the dimensions the
-- dashboard needs, Ist-Daten is aggregated on the fly during ingestion, and the
-- live GTFS-RT feed keeps one "current state" row per station plus a small
-- national time series.

create extension if not exists postgis;

create schema if not exists transit;

-- ---------------------------------------------------------------------------
-- Ingestion bookkeeping
-- ---------------------------------------------------------------------------

create table if not exists transit.ingestion_run (
    run_id        bigint generated always as identity primary key,
    source        text        not null,  -- 'gtfs_static' | 'istdaten' | 'gtfs_rt'
    resource_key  text,                  -- file name / feed version / service day
    started_at    timestamptz not null default now(),
    finished_at   timestamptz,
    status        text        not null default 'running',  -- running | ok | failed | skipped
    rows_in       bigint,
    rows_out      bigint,
    message       text
);

create index if not exists ingestion_run_source_idx
    on transit.ingestion_run (source, started_at desc);

-- ---------------------------------------------------------------------------
-- Static dimensions (GTFS static timetable)
-- ---------------------------------------------------------------------------

create table if not exists transit.agency (
    agency_id    text primary key,
    agency_name  text not null,
    agency_url   text
);

create table if not exists transit.route (
    route_id          text primary key,
    agency_id         text,
    route_short_name  text,
    route_long_name   text,
    route_desc        text,          -- in the Swiss feed this holds the product (IC, S, B, T...)
    route_type        integer not null,  -- extended GTFS route types (e.g. 102, 109, 700, 900)
    transport_mode    text not null      -- rail | bus | tram | ship | cableway | other
);

create table if not exists transit.stop (
    stop_id         text primary key,
    stop_name       text not null,
    parent_station  text,
    location_type   smallint not null default 0,
    platform_code   text,
    uic             integer,  -- station number shared with Ist-Daten (BPUIC)
    geom            geography(Point, 4326) not null
);

create index if not exists stop_geom_idx on transit.stop using gist (geom);
create index if not exists stop_uic_idx on transit.stop (uic);
create index if not exists stop_parent_idx on transit.stop (parent_station);

-- One row per physical station, used for the map and to join every fact table.
create or replace view transit.station as
select distinct on (s.uic)
    s.uic,
    s.stop_name,
    s.geom
from transit.stop s
where s.uic is not null
order by s.uic, (s.parent_station is null) desc, s.location_type desc, s.stop_id;

-- ---------------------------------------------------------------------------
-- History: Ist-Daten (actual vs planned), aggregated per service day
-- ---------------------------------------------------------------------------
-- Punctuality follows the Swiss convention: an arrival counts as on time when
-- it is less than 3 minutes late. Only measured events (status REAL) count
-- towards punctuality; estimated ones are tracked separately.

create table if not exists transit.stop_day_stats (
    service_day      date     not null,
    uic              integer  not null,
    transport_mode   text     not null,
    events           integer  not null,  -- planned stop events (pass-throughs excluded)
    measured         integer  not null,  -- events with a measured (REAL) actual time
    on_time          integer  not null,  -- measured & delay < 180 s
    delayed_5min     integer  not null,  -- measured & delay >= 300 s
    cancelled        integer  not null,
    extra_trips      integer  not null,
    delay_sum_s      bigint   not null,  -- sum of positive delays over measured events
    delay_max_s      integer  not null,
    primary key (service_day, uic, transport_mode)
);

create table if not exists transit.line_day_stats (
    service_day      date     not null,
    operator_abbr    text     not null,
    line_text        text     not null,
    transport_mode   text     not null,
    events           integer  not null,
    measured         integer  not null,
    on_time          integer  not null,
    delayed_5min     integer  not null,
    cancelled        integer  not null,
    trips            integer  not null,
    delay_sum_s      bigint   not null,
    delay_max_s      integer  not null,
    primary key (service_day, operator_abbr, line_text, transport_mode)
);

create table if not exists transit.hour_day_stats (
    service_day      date     not null,
    hour_of_day      smallint not null,
    transport_mode   text     not null,
    events           integer  not null,
    measured         integer  not null,
    on_time          integer  not null,
    delayed_5min     integer  not null,
    cancelled        integer  not null,
    delay_sum_s      bigint   not null,
    primary key (service_day, hour_of_day, transport_mode)
);

-- ---------------------------------------------------------------------------
-- Live: GTFS-RT trip updates
-- ---------------------------------------------------------------------------

-- One summary row per feed snapshot: the national "pulse" chart.
create table if not exists transit.rt_snapshot (
    observed_at        timestamptz primary key,  -- feed header timestamp
    feed_version       text,
    trips              integer not null,
    trips_cancelled    integer not null,
    stop_updates       integer not null,
    avg_delay_s        numeric(8, 1),
    share_delayed_3min numeric(5, 4)
);

-- Current state per station (upserted each run): what the live map colours.
create table if not exists transit.rt_station_live (
    uic                 integer primary key,
    observed_at         timestamptz not null,
    upcoming_events     integer not null,
    avg_delay_s         numeric(8, 1),
    max_delay_s         integer,
    delayed_3min        integer not null,
    skipped             integer not null
);

-- ---------------------------------------------------------------------------
-- Convenience views for the API and Power BI
-- ---------------------------------------------------------------------------

create or replace view transit.v_stop_punctuality as
select
    d.service_day,
    d.uic,
    st.stop_name,
    d.transport_mode,
    d.events,
    d.measured,
    d.cancelled,
    round(d.on_time::numeric / nullif(d.measured, 0), 4)       as punctuality,
    round(d.delay_sum_s::numeric / nullif(d.measured, 0), 1)   as avg_delay_s,
    st.geom
from transit.stop_day_stats d
left join transit.station st on st.uic = d.uic;

create or replace view transit.v_live_map as
select
    l.uic,
    st.stop_name,
    l.observed_at,
    l.upcoming_events,
    l.avg_delay_s,
    l.max_delay_s,
    l.delayed_3min,
    l.skipped,
    st.geom
from transit.rt_station_live l
join transit.station st on st.uic = l.uic;
