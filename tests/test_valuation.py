import math

import pytest

from app import urbanity
from app.costs import BUILDING_COSTS
from app.data import USAGE
from app.model_params import DEFAULTS
from app.valuation import (
    HousingPrice,
    estimate,
    guess_usage,
    nice_round,
    size_multiplier,
)

# Gerçek örnekler: TCMB'nin 2026 2. çeyrek il konut fiyatları
SAMSUN = HousingPrice(province="Samsun", value=37_326, period="2026 2. çeyrek", source="test", live=True, estimated=False)
BURSA = HousingPrice(province="Bursa", value=41_264, period="2026 2. çeyrek", source="test", live=True, estimated=False)


def place(class_code: int) -> urbanity.Urbanity:
    return urbanity.Urbanity(
        class_code=class_code,
        label=urbanity.CLASS_LABELS[class_code],
        density=0.0,
        nearby_class=class_code,
        province_centre=None,
        district_centre=None,
        settlement=None,
    )


def factor(result, key):
    return next(f for f in result.factors if f.key == key)


def width(result):
    return (result.high - result.low) / result.total


def test_city_parcel_is_valued_with_the_development_method():
    result = estimate(
        area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.URBAN_CENTRE), kaks=1.5,
    )
    development = result.development

    assert result.basis == "gelistirme"
    assert development.buildable_m2 == 1500
    assert development.sellable_m2 == 1200
    assert development.construction_cost == BUILDING_COSTS["III-A"]  # Bursa fiyat bandı
    # Müteahhit yeni daire satar; hasılat il ortalamasının üstünden hesaplanır
    assert development.housing_price > BURSA.value
    assert development.revenue == pytest.approx(development.sellable_m2 * development.housing_price, rel=0.01)
    assert development.land_value == pytest.approx(
        development.revenue - development.cost - development.developer_share, rel=0.01
    )
    assert development.viable is True
    assert result.unit_price > 5_000
    assert "inşaat hakkı" in result.base_detail


def test_village_parcel_falls_back_to_the_floor_value():
    # Samsun Alaçam'da köy içi 700 m² imarlı parsel, emsal 0,50: satış fiyatı inşaat
    # maliyetini karşılamadığı için geliştirme hesabı arsaya değer bırakmaz.
    result = estimate(
        area_m2=700, usage="konut", housing=SAMSUN, urban=place(urbanity.VERY_LOW_RURAL), kaks=0.5,
    )

    assert result.basis == "taban"
    assert result.development.viable is False
    assert result.base_label == "Taban değer"
    assert 100 < result.unit_price < 1_000       # köyde arsa m² fiyatı bu aralıkta beklenir
    assert result.confidence in ("orta", "düşük")


def test_city_land_is_worth_much_more_than_village_land():
    city = estimate(area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.URBAN_CENTRE), kaks=1.5)
    village = estimate(area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.VILLAGE), kaks=1.5)
    rural = estimate(area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.VERY_LOW_RURAL), kaks=1.5)

    assert city.unit_price > village.unit_price > rural.unit_price


def test_higher_kaks_raises_the_value_of_zoned_land():
    def city(kaks):
        return estimate(area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.URBAN_CENTRE), kaks=kaks)

    assert city(2.0).total > city(1.5).total > city(1.0).total


def test_unknown_kaks_is_assumed_and_widens_the_range():
    given = estimate(area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.URBAN_CENTRE), kaks=1.5)
    assumed = estimate(area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.URBAN_CENTRE))

    assert assumed.development.kaks_assumed is True
    assert assumed.development.kaks == DEFAULTS.default_kaks[urbanity.URBAN_CENTRE]
    assert width(assumed) > width(given)


def test_farmland_is_valued_as_a_ratio_of_local_housing_prices():
    field = estimate(area_m2=5000, usage="tarla", housing=SAMSUN, urban=place(urbanity.LOW_RURAL))
    orchard = estimate(area_m2=5000, usage="zeytinlik", housing=SAMSUN, urban=place(urbanity.LOW_RURAL))

    assert field.basis == "arazi"
    assert field.development is None
    assert orchard.unit_price > field.unit_price      # zeytinlik tarladan pahalı
    assert "konut fiyatının" in field.base_detail


def test_receipt_adds_up():
    result = estimate(
        area_m2=467.87, usage="konut", housing=BURSA, urban=place(urbanity.DENSE_CLUSTER),
        kaks=1.2, deed="tam", road="var", utilities="var",
    )
    product = result.base_price * math.prod(f.multiplier for f in result.factors)

    assert result.unit_price == nice_round(product)
    assert result.total == nice_round(result.unit_price * 467.87)
    assert result.low < result.total < result.high
    assert result.settlement == "yoğun kentsel küme"
    assert result.housing.province == "Bursa"


def test_estimates_are_deterministic():
    arguments = dict(area_m2=800, usage="konut", housing=BURSA, urban=place(urbanity.TOWN), kaks=1.0)
    assert estimate(**arguments) == estimate(**arguments)


@pytest.mark.parametrize(
    ("answer", "key"),
    [
        (dict(deed="hisseli"), "deed"),
        (dict(road="yok"), "road"),
        (dict(utilities="yok"), "utilities"),
    ],
)
def test_negative_answers_lower_the_value(answer, key):
    base = dict(area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.TOWN), kaks=1.0)
    good = estimate(**base, deed="tam", road="var", utilities="var")
    worse = estimate(**base, **({"deed": "tam", "road": "var", "utilities": "var"} | answer))

    assert worse.total < good.total
    assert factor(worse, key).multiplier < 1


def test_view_and_corner_only_count_when_answered():
    base = dict(area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.SUBURBAN), kaks=1.0)
    plain = estimate(**base)
    extras = estimate(**base, view="var", corner="evet")

    assert "view" not in [f.key for f in plain.factors]
    assert extras.total > plain.total


def test_irrigation_only_applies_to_unzoned_land():
    zoned = estimate(area_m2=1000, usage="konut", housing=SAMSUN, urban=place(urbanity.TOWN), irrigation="sulu")
    unzoned = estimate(area_m2=5000, usage="tarla", housing=SAMSUN, urban=place(urbanity.LOW_RURAL), irrigation="sulu")

    assert "irrigation" not in [f.key for f in zoned.factors]
    assert factor(unzoned, "irrigation").multiplier > 1


def test_missing_data_widens_the_range_and_lowers_confidence():
    known = estimate(
        area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.URBAN_CENTRE),
        kaks=1.5, deed="tam", road="var", utilities="var",
    )
    copy_price = HousingPrice(province="Bursa", value=41_264, period="2026 2. çeyrek",
                              source="kopya", live=False, estimated=True)
    unknown = estimate(area_m2=1000, usage="konut", housing=copy_price, urban=None)

    assert known.confidence == "yüksek"
    assert unknown.confidence == "düşük"
    assert width(unknown) > width(known)


def test_sale_scenarios_bracket_the_market_value():
    result = estimate(area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.URBAN_CENTRE), kaks=1.5)
    scenarios = {s.key: s for s in result.scenarios}

    assert list(scenarios) == ["acil", "piyasa", "tok"]
    assert scenarios["acil"].value < scenarios["piyasa"].value < scenarios["tok"].value
    assert (scenarios["piyasa"].value, scenarios["piyasa"].low) == (result.total, result.low)


def test_shared_deed_reports_the_value_of_the_share():
    result = estimate(
        area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.TOWN), kaks=1.0,
        deed="hisseli", share_pct=25,
    )
    assert result.share_pct == 25
    assert result.share_value == pytest.approx(result.total * 0.25, rel=0.02)


@pytest.mark.parametrize(
    "bad",
    [dict(area_m2=0), dict(usage="havaalanı"), dict(kaks=0), dict(deed="yarım"),
     dict(road="belki"), dict(utilities="?"), dict(view="belki"), dict(corner="?"),
     dict(irrigation="yarı"), dict(share_pct=150)],
)
def test_invalid_input_is_rejected(bad):
    arguments = dict(area_m2=1000, usage="konut", housing=BURSA, urban=place(urbanity.TOWN)) | bad
    with pytest.raises(ValueError):
        estimate(**arguments)


@pytest.mark.parametrize(
    ("nitelik", "usage"),
    [
        ("Arsa", "konut"),
        ("7 Adet Kargir Bina", "konut"),
        ("Kargir Dükkan ve Arsa", "ticari"),
        ("Fabrika", "sanayi"),
        ("Tarla", "tarla"),
        ("Zeytinlik", "zeytinlik"),
        ("Fındık Bahçesi", "bag_bahce"),
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


def test_size_multiplier_is_bounded_and_decreasing():
    values = [size_multiplier(area) for area in (50, 500, 5_000, 50_000, 5_000_000)]
    assert values == sorted(values, reverse=True)
    assert size_multiplier(500) == pytest.approx(1.0)
    assert 0.65 <= min(values) and max(values) <= 1.08


def test_every_usage_can_be_valued():
    for usage in USAGE:
        result = estimate(area_m2=1000, usage=usage, housing=BURSA, urban=place(urbanity.TOWN))
        assert result.total > 0
