-- Some Ist-Daten stops carried a 9-digit BPUIC (7-digit station number + 2-digit
-- suffix), stored as-is before the ingestion normalised it. Fold those rows into
-- their station so they get a name and a map point.

insert into transit.stop_day_stats as t (
    service_day, uic, transport_mode, events, measured, on_time, delayed_5min,
    cancelled, extra_trips, delay_sum_s, delay_max_s
)
select
    service_day, uic / 100, transport_mode, sum(events), sum(measured), sum(on_time),
    sum(delayed_5min), sum(cancelled), sum(extra_trips), sum(delay_sum_s), max(delay_max_s)
from transit.stop_day_stats
where uic >= 100000000
group by service_day, uic / 100, transport_mode
on conflict (service_day, uic, transport_mode) do update set
    events       = t.events + excluded.events,
    measured     = t.measured + excluded.measured,
    on_time      = t.on_time + excluded.on_time,
    delayed_5min = t.delayed_5min + excluded.delayed_5min,
    cancelled    = t.cancelled + excluded.cancelled,
    extra_trips  = t.extra_trips + excluded.extra_trips,
    delay_sum_s  = t.delay_sum_s + excluded.delay_sum_s,
    delay_max_s  = greatest(t.delay_max_s, excluded.delay_max_s);

delete from transit.stop_day_stats where uic >= 100000000;
