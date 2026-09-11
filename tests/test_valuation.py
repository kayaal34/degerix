import math
from typing import get_args

import pytest

from app.data import (
    DEED,
    PROVINCE_BASE_PRICE,
    ROAD,
    UNKNOWN,
    USAGE,
    UTILITIES,
    DeedKey,
    RoadKey,
    UsageKey,
    UtilitiesKey,
    district_factor,
    fold,
    province_base_price,
)
from app.geo import centroid_and_area, haversine_km
from app.tkgm import parse_area
from app.valuation import (
    DistrictArea,
    estimate,
    guess_usage,
    kaks_multiplier,
    location_multiplier,
    nice_round,
    size_multiplier,
)

BODRUM = dict(
    province="Muğla", district="Bodrum", area_m2=467.87, usage="konut",
    lat=37.0385, lng=27.419, district_area=DistrictArea(lat=37.05, lng=27.40, area_km2=560),
)
ANSWERED = dict(kaks=1.5, deed="tam", road="var", utilities="var")


def factor(result, key):
    return next(f for f in result.factors if f.key == key)


def width(result):
    return (result.high - result.low) / result.total


def test_reference_data_is_complete():
    assert len(PROVINCE_BASE_PRICE) == 81
    assert set(get_args(UsageKey)) == set(USAGE)
    assert set(get_args(DeedKey)) == set(DEED) | {UNKNOWN}
    assert set(get_args(RoadKey)) == set(ROAD) | {UNKNOWN}
    assert set(get_args(UtilitiesKey)) == set(UTILITIES) | {UNKNOWN}


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


def test_kaks_multiplier_is_bounded_and_increasing():
    values = [kaks_multiplier(k) for k in (0.1, 0.5, 1.0, 2.0, 5.0)]
    assert values == sorted(values)
    assert kaks_multiplier(1.0) == pytest.approx(1.0)
    assert (values[0], values[-1]) == (0.5, 1.8)


def test_estimate_is_deterministic_and_self_consistent():
    first, second = estimate(**BODRUM, **ANSWERED), estimate(**BODRUM, **ANSWERED)
    assert first == second

    product = first.base_price * math.prod(f.multiplier for f in first.factors)
    assert first.unit_price == nice_round(product)
    assert first.total == nice_round(first.unit_price * 467.87)
    assert first.low < first.total < first.high
    assert first.confidence == "yüksek"
    assert [f.key for f in first.factors] == ["district", "location", "usage", "kaks", "size", "deed", "road", "utilities"]


def test_kaks_raises_value_and_reports_buildable_area():
    assert estimate(**BODRUM, kaks=2.0).total > estimate(**BODRUM, kaks=0.5).total
    result = estimate(province="Konya", district="Meram", area_m2=1000, usage="konut", kaks=1.5)
    assert factor(result, "kaks").detail == "1,50 → 1.500 m² inşaat hakkı"


def test_kaks_is_ignored_for_unzoned_land():
    with_kaks = estimate(province="Konya", district="Meram", area_m2=5000, usage="tarla", kaks=2.0)
    without = estimate(province="Konya", district="Meram", area_m2=5000, usage="tarla")
    assert "kaks" not in [f.key for f in with_kaks.factors]
    assert with_kaks == without


@pytest.mark.parametrize(
    ("answer", "key"),
    [(dict(deed="hisseli"), "deed"), (dict(road="yok"), "road"), (dict(utilities="kismen"), "utilities"), (dict(utilities="yok"), "utilities")],
)
def test_negative_answers_lower_value(answer, key):
    best = estimate(**BODRUM, **ANSWERED)
    worse = estimate(**BODRUM, **(ANSWERED | answer))
    assert worse.total < best.total
    assert factor(worse, key).multiplier < 1


def test_answering_questions_narrows_range_without_changing_value():
    unanswered = estimate(**BODRUM, kaks=1.5)
    answered = estimate(**BODRUM, **ANSWERED)

    assert answered.unit_price == unanswered.unit_price  # "var" / "müstakil" referansla aynı
    assert width(answered) < width(unanswered)
    assert factor(unanswered, "road").detail == "Yanıtlanmadı, aralık genişletildi"


def test_confidence_follows_how_much_is_known():
    assert estimate(**BODRUM, **ANSWERED).confidence == "yüksek"
    assert estimate(**BODRUM).confidence == "orta"
    assert estimate(province="Muğla", district="Ula", area_m2=1000, usage="tarla").confidence == "düşük"


def test_missing_data_widens_range():
    known = estimate(**BODRUM)
    unknown = estimate(province="Muğla", district="Ula", area_m2=1000, usage="tarla")
    assert width(unknown) > width(known)


def test_shared_deed_reports_value_of_share():
    result = estimate(**BODRUM, **(ANSWERED | dict(deed="hisseli", share_pct=25)))
    assert result.share_pct == 25
    assert result.share_value == nice_round(result.unit_price * 467.87 * 0.25)
    # müstakil tapuda girilen pay yok sayılır
    assert estimate(**BODRUM, **(ANSWERED | dict(share_pct=25))).share_value is None


def test_missing_utilities_matter_less_on_unzoned_land():
    zoned = estimate(province="Konya", district="Meram", area_m2=1000, usage="konut", utilities="yok")
    unzoned = estimate(province="Konya", district="Meram", area_m2=1000, usage="tarla", utilities="yok")
    assert factor(unzoned, "utilities").multiplier > factor(zoned, "utilities").multiplier


def test_sale_scenarios_bracket_market_value():
    result = estimate(**BODRUM, **ANSWERED)
    scenarios = {s.key: s for s in result.scenarios}

    assert list(scenarios) == ["acil", "piyasa", "tok"]
    assert scenarios["acil"].value < scenarios["piyasa"].value < scenarios["tok"].value
    market = scenarios["piyasa"]
    assert (market.value, market.low, market.high) == (result.total, result.low, result.high)
    assert all(s.low < s.value < s.high for s in result.scenarios)


def test_urgent_sale_discount_is_deeper_on_unzoned_land():
    def urgent_ratio(usage):
        scenarios = {s.key: s for s in estimate(province="Konya", district="Meram", area_m2=1000, usage=usage).scenarios}
        return scenarios["acil"].value / scenarios["piyasa"].value

    assert urgent_ratio("tarla") < urgent_ratio("konut")


def test_usage_changes_value_in_expected_direction():
    values = {usage: estimate(province="Konya", district="Meram", area_m2=1000, usage=usage).total for usage in USAGE}
    assert values["ticari"] > values["konut"] > values["sanayi"] > values["tarla"]


@pytest.mark.parametrize(
    "bad",
    [dict(area_m2=0), dict(usage="havaalanı"), dict(kaks=0), dict(deed="yarım"),
     dict(road="belki"), dict(utilities="?"), dict(share_pct=150)],
)
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
