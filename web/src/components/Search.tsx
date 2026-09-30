import { useEffect, useState } from "react";
import { api } from "../api";

export function Search({ onSelect }: { onSelect: (uic: number) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<{ uic: number; name: string }[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const ctrl = new AbortController();
    const t = window.setTimeout(() => {
      api.search(q.trim(), ctrl.signal).then(setHits, () => undefined);
    }, 200);
    return () => {
      window.clearTimeout(t);
      ctrl.abort();
    };
  }, [q]);

  const pick = (uic: number) => {
    onSelect(uic);
    setQ("");
    setOpen(false);
  };

  return (
    <div className="search">
      <input
        type="search"
        placeholder="Find a station…"
        aria-label="Find a station"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onKeyDown={(e) => e.key === "Enter" && hits[0] && pick(hits[0].uic)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
      />
      {open && hits.length > 0 && (
        <ul className="search-hits" role="listbox">
          {hits.map((h) => (
            <li key={h.uic} role="option" aria-selected={false} onMouseDown={() => pick(h.uic)}>
              {h.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
