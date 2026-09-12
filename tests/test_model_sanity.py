"""
Modelin akıl sağlığı: elde etiketli fiyat verisi olmadan da saçma sonuçları yakalar.

Ağa çıkmaz; konut fiyatı depodaki TCMB kopyasından, yerleşim sınıfı statik ızgaradan
okunur. Aynı kurallar tools/sanity_check.py ile elle de çalıştırılabilir.
"""

import pytest

from app import urbanity
from app.market import snapshot_price
from app.valuation import estimate

ANSWERS = dict(deed="tam", road="var", utilities="var", view="yok")
AREA = 1000.0

# Aynı il içinde kentsellikten başka her şey sabit: konut fiyatı değişmez, fark yerleşimden gelir
BURSA = [
    ("Nilüfer merkez", 40.2140, 28.9157),
    ("Mudanya", 40.3752, 28.8838),
    ("Kestel çeperi", 40.1980, 29.2100),
    ("Gölyazı", 40.1690, 28.6820),
    ("kırsal", 39.9800, 29.2400),
]


def value_at(province: str, lat: float, lng: float, **overrides):
    housing = snapshot_price(province)
    assert housing is not None, f"{province} için konut fiyatı kopyası yok"
    context = urbanity.describe(lat, lng)
    assert context is not None, f"{province} noktası kentsellik ızgarasının dışında"
    fields = dict(area_m2=AREA, usage="konut", kaks=1.0) | ANSWERS | overrides
    return estimate(housing=housing, urban=context, **fields), context


def test_sample_points_are_inside_the_grid():
    for label, lat, lng in BURSA:
        _, context = value_at("Bursa", lat, lng)
        assert context.label, label


def test_value_falls_from_city_centre_to_countryside():
    rows = [(label, *value_at("Bursa", lat, lng)) for label, lat, lng in BURSA]
    rows.sort(key=lambda row: row[2].class_code, reverse=True)

    for (upper_label, upper, upper_context), (lower_label, lower, lower_context) in zip(rows, rows[1:]):
        if upper_context.class_code == lower_context.class_code:
            continue
        assert upper.unit_price >= lower.unit_price, (
            f"{upper_label} ({upper_context.label}) {upper.unit_price} < "
            f"{lower_label} ({lower_context.label}) {lower.unit_price}"
        )


def test_city_centre_is_far_above_countryside():
    city, _ = value_at("Bursa", *BURSA[0][1:])
    country, _ = value_at("Bursa", *BURSA[-1][1:])
    assert city.unit_price > 5 * country.unit_price


@pytest.mark.parametrize(("label", "lat", "lng"), BURSA)
def test_zoned_land_is_worth_more_than_farmland(label, lat, lng):
    zoned, _ = value_at("Bursa", lat, lng)
    farmland, _ = value_at("Bursa", lat, lng, usage="tarla", kaks=None)
    assert zoned.unit_price > farmland.unit_price


def test_value_rises_with_building_rights():
    low, _ = value_at("Bursa", *BURSA[0][1:], kaks=0.5)
    middle, _ = value_at("Bursa", *BURSA[0][1:], kaks=1.0)
    high, _ = value_at("Bursa", *BURSA[0][1:], kaks=2.0)
    assert low.unit_price < middle.unit_price < high.unit_price


def test_unit_price_falls_on_large_parcels():
    small, _ = value_at("Bursa", *BURSA[0][1:], area_m2=1_000)
    large, _ = value_at("Bursa", *BURSA[0][1:], area_m2=20_000)
    assert large.unit_price < small.unit_price


@pytest.mark.parametrize(("label", "lat", "lng"), BURSA)
def test_range_contains_the_estimate(label, lat, lng):
    result, _ = value_at("Bursa", lat, lng)
    assert 0 < result.low < result.total < result.high


def test_development_method_in_city_and_floor_in_countryside():
    city, _ = value_at("Bursa", *BURSA[0][1:])
    country, _ = value_at("Bursa", *BURSA[-1][1:])
    assert city.basis == "gelistirme"
    assert country.basis == "taban"
