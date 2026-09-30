import { useEffect, useState } from "react";

export interface Loadable<T> {
  data: T | undefined;
  error: string | null;
  loading: boolean;
}

/**
 * Fetch when `deps` change and, if `refreshMs` is set, poll on that interval.
 * Keeps the previous data while reloading so charts don't flash empty.
 */
export function useData<T>(
  load: ((signal: AbortSignal) => Promise<T>) | null,
  deps: unknown[],
  refreshMs?: number,
): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ data: undefined, error: null, loading: !!load });

  useEffect(() => {
    if (!load) return;
    let ctrl = new AbortController();
    const run = () => {
      ctrl.abort();
      ctrl = new AbortController();
      const signal = ctrl.signal;
      setState((s) => ({ ...s, loading: true }));
      load(signal).then(
        (data) => !signal.aborted && setState({ data, error: null, loading: false }),
        (err: unknown) => {
          if (signal.aborted) return;
          setState((s) => ({ ...s, error: err instanceof Error ? err.message : String(err), loading: false }));
        },
      );
    };
    run();
    const timer = refreshMs ? window.setInterval(run, refreshMs) : undefined;
    return () => {
      ctrl.abort();
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}

/** Re-render every `ms` so relative times ("4 min ago") stay current. */
export function useNow(ms = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(t);
  }, [ms]);
  return now;
}

/** Tracks the OS colour scheme so canvas charts and the basemap can switch with it. */
export function useDarkMode(): boolean {
  const query = "(prefers-color-scheme: dark)";
  const [dark, setDark] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setDark(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return dark;
}
