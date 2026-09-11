import asyncio
import math

import pytest

from app import nearby
from app.geo import distance_to_line_m
from app.surroundings import (
    OsmContext,
    Surroundings,
    coast_multiplier,
    factor_rows,
    main_road_multiplier,
    services_multiplier,
    slope_multiplier,
)
from app.valuation import estimate


def test_distance_to_line():
    line = [(37.001, 27.0), (37.001, 27.02)]
    assert distance_to_line_m(37.0, 27.01, line) == pytest.approx(110.6, rel=0.01)   # çizgiye dik
    assert distance_to_line_m(37.0, 27.03, line) == pytest.approx(895.9, rel=0.01)   # uç noktaya
    assert distance_to_line_m(37.0, 27.01, [(37.0, 27.01)]) == 0
    assert math.isinf(distance_to_line_m(37.0, 27.0, []))


def test_multipliers_are_bounded_and_monotonic():
    coast = [coast_multiplier(d) for d in (0, 500, 1500, 3000)]
    assert coast == sorted(coast, reverse=True)
    assert coast[0] == pytest.approx(1.2) and coast[-1] < 1.01
    assert coast_multiplier(None) == 1.0
    assert [main_road_multiplier(d) for d in (50, 500, 1200, None)] == [1.05, 1.0, 0.95, 0.90]
    assert (services_multiplier(0), services_multiplier(6), services_multiplier(40)) == pytest.approx((0.95, 1.0, 1.05))
    assert (slope_multiplier(2), slope_multiplier(15), slope_multiplier(60)) == pytest.approx((1.0, 0.925, 0.85))


def test_surroundings_add_explained_factors():
    measured = Surroundings(osm=OsmContext(coast_m=420, main_road_m=None, services=3), slope_pct=12.4)
    rows = {key: (multiplier, detail) for key, _, multiplier, detail in factor_rows(measured)}

    assert rows["coast"][1] == "Kıyıya 420 m"
    assert rows["main_road"] == (0.90, "1,5 km içinde ana yol yok")
    assert rows["services"][1] == "1 km içinde 3 okul, sağlık ya da market noktası"
    assert rows["slope"][1] == "Yaklaşık %12"

    plain = estimate(province="Bursa", district="Mudanya", area_m2=800, usage="konut")
    with_surroundings = estimate(province="Bursa", district="Mudanya", area_m2=800, usage="konut", surroundings=measured)
    assert [f.key for f in with_surroundings.factors][2:6] == ["coast", "main_road", "services", "slope"]
    product = math.prod(multiplier for multiplier, _ in rows.values())
    assert with_surroundings.unit_price == pytest.approx(plain.unit_price * product, rel=0.02)


def test_unavailable_measurements_are_skipped():
    assert factor_rows(Surroundings(osm=None, slope_pct=None)) == []
    assert [row[0] for row in factor_rows(Surroundings(osm=None, slope_pct=3.0))] == ["slope"]


def test_parse_overpass_classifies_elements():
    data = {"elements": [
        {"type": "way", "tags": {"natural": "coastline"}, "geometry": [{"lat": 40.001, "lon": 28.9}, {"lat": 40.001, "lon": 28.92}]},
        {"type": "way", "tags": {"highway": "primary"}, "geometry": [{"lat": 40.0, "lon": 28.905}, {"lat": 40.0, "lon": 28.915}]},
        {"type": "node", "tags": {"amenity": "school"}},
        {"type": "way", "tags": {"shop": "supermarket"}, "center": {"lat": 40.0, "lon": 28.91}},
    ]}
    assert nearby.parse_overpass(data, 40.0, 28.91) == OsmContext(coast_m=111, main_road_m=0, services=2)


def test_fetch_caches_only_complete_results(monkeypatch):
    nearby.clear_cache()
    calls = []

    async def osm(client, lat, lng):
        calls.append("osm")
        return OsmContext(coast_m=None, main_road_m=200, services=5)

    async def slope_unavailable(client, lat, lng):
        return None

    async def slope(client, lat, lng):
        return 4.0

    monkeypatch.setattr(nearby, "_osm_context", osm)
    monkeypatch.setattr(nearby, "_slope_pct", slope_unavailable)
    first = asyncio.run(nearby.fetch(40.2, 28.9))
    assert first.slope_pct is None and first.osm.services == 5
    asyncio.run(nearby.fetch(40.2, 28.9))
    assert calls.count("osm") == 2  # eksik sonuç saklanmadı

    monkeypatch.setattr(nearby, "_slope_pct", slope)
    asyncio.run(nearby.fetch(40.2, 28.9))
    asyncio.run(nearby.fetch(40.2, 28.9))
    assert calls.count("osm") == 3  # tam sonuç önbellekten geldi
    nearby.clear_cache()


def test_estimate_endpoint_uses_surroundings(client, monkeypatch):
    async def fake_fetch(lat, lng):
        return Surroundings(osm=OsmContext(coast_m=300, main_road_m=100, services=8), slope_pct=2.0)

    monkeypatch.setattr(nearby, "fetch", fake_fetch)
    body = client.post("/api/estimate", json={
        "province": "Muğla", "district": "Bodrum", "area_m2": 500, "usage": "konut", "lat": 37.0385, "lng": 27.419,
    }).json()
    assert {"coast", "main_road", "services", "slope"} <= {f["key"] for f in body["factors"]}
