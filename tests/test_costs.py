import pytest

from app import urbanity
from app.costs import BUILDING_COSTS, CLASS_DESCRIPTIONS, construction_cost


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
    ("usage", "class_code", "expected"),
    [
        ("konut", urbanity.URBAN_CENTRE, ("III-B", 21_050)),
        ("konut", urbanity.TOWN, ("III-A", 19_800)),
        ("konut", urbanity.SUBURBAN, ("III-A", 19_800)),
        ("konut", urbanity.VILLAGE, ("II-C", 15_100)),
        ("konut", urbanity.VERY_LOW_RURAL, ("II-C", 15_100)),
        ("ticari", urbanity.URBAN_CENTRE, ("III-C", 23_400)),
        ("ticari", urbanity.TOWN, ("III-B", 21_050)),
        ("sanayi", urbanity.URBAN_CENTRE, ("II-C", 15_100)),
    ],
)
def test_construction_cost_depends_on_usage_and_settlement(usage, class_code, expected):
    assert construction_cost(usage, class_code) == expected


def test_village_house_is_cheaper_to_build_than_a_city_flat():
    _, village = construction_cost("konut", urbanity.VERY_LOW_RURAL)
    _, city = construction_cost("konut", urbanity.URBAN_CENTRE)
    assert village < city
