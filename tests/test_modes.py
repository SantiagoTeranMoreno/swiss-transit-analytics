import pytest

from sta_ingest.modes import (
    mode_from_product,
    mode_from_route_type,
    uic_from_bpuic,
    uic_from_stop_id,
)


@pytest.mark.parametrize(
    ("stop_id", "uic"),
    [
        ("8503000", 8503000),
        ("8503000:0:3", 8503000),
        ("ch:1:sloid:7000", 8507000),
        ("ch:1:sloid:7000:1:5", 8507000),
        ("ch:1:sloid:91123:0:1", 8591123),
        ("1100008", None),  # foreign station
        ("", None),
        (None, None),
    ],
)
def test_uic_from_stop_id(stop_id, uic):
    assert uic_from_stop_id(stop_id) == uic


def test_uic_from_bpuic():
    assert uic_from_bpuic("8503000") == 8503000
    assert uic_from_bpuic("3000") == 8503000
    assert uic_from_bpuic("", "ch:1:sloid:7000:1:5") == 8507000
    assert uic_from_bpuic("ch:1:sloid:7000") == 8507000


@pytest.mark.parametrize(
    ("route_type", "mode"),
    [
        (102, "rail"),
        (109, "rail"),
        (700, "bus"),
        (900, "tram"),
        (1000, "ship"),
        (1300, "cableway"),
        (1400, "cableway"),
        (3, "bus"),
        (0, "tram"),
        (1700, "other"),
    ],
)
def test_mode_from_route_type(route_type, mode):
    assert mode_from_route_type(route_type) == mode


@pytest.mark.parametrize(
    ("product", "mode"),
    [
        ("Zug", "rail"),
        ("Zahnradbahn", "rail"),
        ("Bus", "bus"),
        ("Tram", "tram"),
        ("Metro", "metro"),
        ("Schiff", "ship"),
        ("Standseilbahn", "cableway"),
        ("Luftseilbahn", "cableway"),
        ("", "other"),
        (None, "other"),
    ],
)
def test_mode_from_product(product, mode):
    assert mode_from_product(product) == mode
