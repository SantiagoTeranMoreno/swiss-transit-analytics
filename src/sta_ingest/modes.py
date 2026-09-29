"""Normalisation helpers shared by all sources: transport modes and station numbers."""

from __future__ import annotations

import re

MODES = ("rail", "bus", "tram", "metro", "ship", "cableway", "other")


def mode_from_route_type(route_type: int) -> str:
    """Map a GTFS route_type (basic or extended) to a coarse transport mode."""
    basic = {
        0: "tram",
        1: "metro",
        2: "rail",
        3: "bus",
        4: "ship",
        5: "cableway",
        6: "cableway",
        7: "cableway",
        11: "bus",
        12: "rail",
    }
    if route_type in basic:
        return basic[route_type]
    family = route_type // 100
    return {
        1: "rail",  # 100-117 railway services
        2: "bus",  # 200-209 coach
        4: "metro",  # 400-405 urban railway
        7: "bus",  # 700-716 bus
        8: "bus",  # 800 trolleybus
        9: "tram",  # 900-906 tram
        10: "ship",  # 1000 water transport
        12: "ship",  # 1200 ferry
        13: "cableway",  # 1300 aerial lift
        14: "cableway",  # 1400 funicular
    }.get(family, "other")


def mode_from_product(product: str | None) -> str:
    """Map an Ist-Daten PRODUKT_ID (German product name) to a coarse transport mode."""
    p = (product or "").strip().lower()
    if not p:
        return "other"
    if p in {"zug", "train"} or ("bahn" in p and "seil" not in p):
        return "rail"
    if p.startswith("bus") or p in {"car", "nachtbus"}:
        return "bus"
    if p.startswith("tram"):
        return "tram"
    if p.startswith("metro"):
        return "metro"
    if p in {"schiff", "bat", "boot"}:
        return "ship"
    if "seil" in p or "lift" in p:
        return "cableway"
    return "other"


_NUMERIC_ID = re.compile(r"^(85\d{5})(?::|$)")
_SLOID_ID = re.compile(r"^ch:1:sloid:(\d{1,5})(?::|$)")


def uic_from_stop_id(stop_id: str | None) -> int | None:
    """Derive the 7-digit Swiss station number (UIC/BPUIC) from a GTFS stop_id or SLOID.

    The Swiss feed uses either numeric ids (``8503000``, ``8503000:0:3``) or, since
    June 2026, SLOIDs (``ch:1:sloid:3000:1:2``). A SLOID's first number is the
    station number without the ``85`` country prefix, so ``3000`` -> ``8503000``.
    """
    if not stop_id:
        return None
    s = stop_id.strip()
    if m := _NUMERIC_ID.match(s):
        return int(m.group(1))
    if m := _SLOID_ID.match(s):
        return 8_500_000 + int(m.group(1))
    return None


def uic_from_bpuic(value: str | None, sloid: str | None = None) -> int | None:
    """Station number from Ist-Daten: BPUIC is usually numeric, but may carry a SLOID in v2."""
    v = (value or "").strip()
    if v.isdigit():
        n = int(v)
        return n if n >= 1_000_000 else 8_500_000 + n
    return uic_from_stop_id(v) or uic_from_stop_id(sloid)
