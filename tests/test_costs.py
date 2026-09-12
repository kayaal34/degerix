import pytest

from app import urbanity
from app.costs import BUILDING_COSTS, CLASS_DESCRIPTIONS, HOUSING_PRICE_BANDS, construction_cost

CITY = urbanity.URBAN_CENTRE
TOWN = urbanity.TOWN
VILLAGE = urbanity.VILLAGE
COUNTRYSIDE = urbanity.VERY_LOW_RURAL


def test_cost_table_matches_the_official_tebligh():
    # Resmî Gazete 3/2/2026, sayı 33157 — birkaç satır örnekle doğrulanır
    assert BUILDING_COSTS["II-C"] == 15_100
    assert BUILDING_COSTS["III-A"] == 19_800
    assert BUILDING_COSTS["III-B"] == 21_050
    assert BUILDING_COSTS["III-C"] == 23_400
    assert len(BUILDING_COSTS) == 18
    assert set(CLASS_DESCRIPTIONS) <= set(BUILDING_COSTS)
    assert sorted(BUILDING_COSTS.values()) == list(BUILDING_COSTS.values())  # ucuzdan pahalıya


@pytest.mark.parametrize(
    ("usage", "class_code", "housing_price", "expected"),
    [
        ("konut", CITY, 90_000, ("III-B", 21_050)),        # konutun pahalı olduğu şehir
        ("konut", CITY, 45_000, ("III-A", 19_800)),        # orta ölçekli şehir
        ("konut", CITY, 25_000, ("II-C", 15_100)),         # konutun ucuz olduğu şehir
        ("konut", TOWN, 40_000, ("III-A", 19_800)),
        ("konut", VILLAGE, 40_000, ("II-C", 15_100)),      # kırsalda köy evi
        ("konut", COUNTRYSIDE, 90_000, ("II-C", 15_100)),  # pahalı bölgede bile kırsal yapı
        ("ticari", CITY, 90_000, ("III-C", 23_400)),
        ("ticari", CITY, 40_000, ("III-B", 21_050)),
        ("ticari", VILLAGE, 90_000, ("III-A", 19_800)),
        ("sanayi", CITY, 90_000, ("II-C", 15_100)),
    ],
)
def test_construction_cost_depends_on_usage_settlement_and_housing_price(usage, class_code, housing_price, expected):
    assert construction_cost(usage, class_code, housing_price) == expected


def test_cheaper_cities_build_cheaper():
    _, cheap = construction_cost("konut", CITY, 24_000)
    _, middle = construction_cost("konut", CITY, 45_000)
    _, expensive = construction_cost("konut", CITY, 90_000)
    assert cheap < middle < expensive


def test_village_house_is_cheaper_to_build_than_a_city_flat():
    _, village = construction_cost("konut", COUNTRYSIDE, 60_000)
    _, city = construction_cost("konut", CITY, 60_000)
    assert village < city


def test_price_bands_run_from_expensive_to_cheap_and_cover_everything():
    thresholds = [threshold for threshold, *_ in HOUSING_PRICE_BANDS]
    assert thresholds == sorted(thresholds, reverse=True)
    assert thresholds[-1] == 0  # en alt bant her fiyatı karşılar
