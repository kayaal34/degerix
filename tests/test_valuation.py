import math
from typing import get_args

import pytest

from app.data import PROVINCE_BASE_PRICE, USAGE, UsageKey, district_factor, fold, province_base_price
from app.geo import centroid_and_area, haversine_km
from app.tkgm import parse_area
from app.valuation import (
    DistrictArea,
    estimate,
    guess_usage,
    location_multiplier,
    nice_round,
    size_multiplier,
)


def test_reference_data_is_complete():
    assert len(PROVINCE_BASE_PRICE) == 81
    assert set(get_args(UsageKey)) == set(USAGE)


@pytest.mark.parametrize(("a", "b"), [("Gölbaşi", "Gölbaşı"), ("İZMİR", "izmir"), ("  Kuşadası ", "kusadasi")])
def test_fold_ignores_turkish_spelling_differences(a, b):
    assert fold(a) == fold(b)


def test_lookups_match_tkgm_spelling():
    assert province_base_price("ISTANBUL") == 13500
    assert district_factor("Ankara", "Gölbaşi") == 1.2
    assert district_factor("Ankara", "Bilinmeyen") is None


@pytest.mark.parametrize(
    ("nitelik", "usage"),
    [
        ("Arsa", "konut"),
        ("7 Adet Kargir Bina", "konut"),
        ("Avlulu Kargir Ev Ve Bahçe", "konut"),
        ("Kargir Dükkan ve Arsa", "ticari"),
        ("Fabrika", "sanayi"),
        ("Tarla", "tarla"),
        ("Zeytinlik", "zeytinlik"),
        ("Fındık Bahçesi", "bag_bahce"),
        ("Bağ", "bag_bahce"),
        (None, "konut"),
    ],
)
def test_guess_usage(nitelik, usage):
    assert guess_usage(nitelik) == usage


@pytest.mark.parametrize(
    ("value", "expected"),
    [(57_432_100, 57_400_000), (20_340.5, 20_300), (999.6, 1_000), (0, 0)],
)
def test_nice_round(value, expected):
    assert nice_round(value) == expected


def test_location_multiplier_decreases_with_distance():
    values = [location_multiplier(d, radius_km=10) for d in (0, 5, 10, 30)]
    assert values[0] == pytest.approx(1.10)
    assert values == sorted(values, reverse=True)
    assert values[-1] > 0.85


def test_size_multiplier_is_bounded_and_decreasing():
    values = [size_multiplier(a) for a in (50, 500, 5_000, 50_000, 5_000_000)]
    assert values == sorted(values, reverse=True)
    assert size_multiplier(500) == pytest.approx(1.0)
    assert 0.65 <= min(values) and max(values) <= 1.08


def test_estimate_is_deterministic_and_self_consistent():
    district = DistrictArea(lat=37.05, lng=27.40, area_km2=560)
    kwargs = dict(province="Muğla", district="Bodrum", area_m2=467.87, usage="konut", lat=37.0385, lng=27.419, district_area=district)

    first, second = estimate(**kwargs), estimate(**kwargs)
    assert first == second

    product = first.base_price * math.prod(f.multiplier for f in first.factors)
    assert first.unit_price == nice_round(product)
    assert first.total == nice_round(first.unit_price * 467.87)
    assert first.low < first.total < first.high
    assert first.confidence == "yüksek"
    assert [f.key for f in first.factors] == ["district", "location", "usage", "size"]


def test_missing_data_widens_range_and_lowers_confidence():
    known = estimate(province="Muğla", district="Bodrum", area_m2=1000, usage="konut",
                     lat=37.04, lng=27.42, district_area=DistrictArea(37.05, 27.40, 560))
    unknown = estimate(province="Muğla", district="Ula", area_m2=1000, usage="tarla")

    assert unknown.confidence == "düşük"
    assert (unknown.high - unknown.low) / unknown.total > (known.high - known.low) / known.total


def test_usage_changes_value_in_expected_direction():
    values = {usage: estimate(province="Konya", district="Meram", area_m2=1000, usage=usage).total for usage in USAGE}
    assert values["ticari"] > values["konut"] > values["sanayi"] > values["tarla"]


@pytest.mark.parametrize("bad", [dict(area_m2=0), dict(usage="havaalanı")])
def test_estimate_rejects_invalid_input(bad):
    kwargs = dict(province="Konya", district="Meram", area_m2=1000, usage="konut") | bad
    with pytest.raises(ValueError):
        estimate(**kwargs)


def test_haversine_known_distance():
    # Ankara Kızılay → İstanbul Taksim yaklaşık 350 km
    assert haversine_km(39.9208, 32.8541, 41.0370, 28.9850) == pytest.approx(350, abs=10)


def test_centroid_and_area_of_square_is_orientation_independent():
    ring = [[27.0, 37.0], [27.1, 37.0], [27.1, 37.1], [27.0, 37.1], [27.0, 37.0]]
    ccw = centroid_and_area({"type": "Polygon", "coordinates": [ring]})
    cw = centroid_and_area({"type": "Polygon", "coordinates": [ring[::-1]]})

    assert ccw == pytest.approx(cw)
    lat, lng, area = ccw
    assert (lat, lng) == pytest.approx((37.05, 27.05), abs=1e-6)
    assert area == pytest.approx(11.06 * 8.89, rel=0.02)  # ~11,06 km × ~8,89 km


def test_centroid_of_multipolygon_weights_by_area():
    big = [[[27.0, 37.0], [27.2, 37.0], [27.2, 37.2], [27.0, 37.2], [27.0, 37.0]]]
    small = [[[28.0, 37.0], [28.02, 37.0], [28.02, 37.02], [28.0, 37.02], [28.0, 37.0]]]
    lat, lng, _ = centroid_and_area({"type": "MultiPolygon", "coordinates": [big, small]})
    assert 27.1 < lng < 27.2  # büyük parçaya çok daha yakın


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("45,911.00", 45911.0), ("45.911,00", 45911.0), ("467.87", 467.87), ("467,87", 467.87),
     ("1.234.567", 1234567.0), ("78,188.20", 78188.2), (512, 512.0), ("", None), ("abc", None), ("0", None)],
)
def test_parse_area_handles_both_number_formats(raw, expected):
    assert parse_area(raw) == expected
