"""
Kentsellik geçişinin yumuşatılması ve kırsalda merkeze yakınlık.

Izgara 1 km çözünürlükte olduğu için köyün kenarındaki parsel "boş kırsal" hücresine
düşebiliyor; bu iki kural o sınırlardaki sertliği alır.
"""

import pytest

from app.market import snapshot_price
from app.model_params import DEFAULTS
from app.urbanity import LOW_RURAL, TOWN, URBAN_CENTRE, VERY_LOW_RURAL, VILLAGE, Place, Urbanity
from app.valuation import blended_locality, centre_proximity, estimate


def urban(class_code: int, nearby: int | None = None, centre_km: float = 12.0) -> Urbanity:
    return Urbanity(
        class_code=class_code,
        label="deneme",
        density=50.0,
        nearby_class=nearby if nearby is not None else class_code,
        province_centre=Place(name="Bursa", code="PPLA", population=1_500_000, distance_km=40.0),
        district_centre=Place(name="Karacabey", code="PPLA2", population=40_000, distance_km=centre_km),
        settlement=Place(name="Deneme", code="PPL", population=0, distance_km=0.4),
    )


def test_locality_is_pulled_towards_a_denser_neighbour():
    alone = blended_locality(urban(VERY_LOW_RURAL), DEFAULTS)
    beside_town = blended_locality(urban(VERY_LOW_RURAL, nearby=TOWN), DEFAULTS)

    assert alone == DEFAULTS.locality[VERY_LOW_RURAL]
    assert alone < beside_town < DEFAULTS.locality[TOWN]


def test_a_quieter_neighbour_does_not_lower_the_value():
    assert blended_locality(urban(TOWN, nearby=VERY_LOW_RURAL), DEFAULTS) == DEFAULTS.locality[TOWN]


def test_locality_falls_back_when_the_grid_has_no_answer():
    assert blended_locality(None, DEFAULTS) == DEFAULTS.locality[LOW_RURAL]


def test_being_close_to_the_district_centre_helps_only_in_the_countryside():
    near = centre_proximity(urban(VILLAGE, centre_km=2.0), DEFAULTS)
    far = centre_proximity(urban(VILLAGE, centre_km=40.0), DEFAULTS)

    assert near.multiplier > far.multiplier > 1.0
    assert near.multiplier <= 1 + DEFAULTS.rural_centre_bonus
    assert "Karacabey" in near.detail
    assert centre_proximity(urban(URBAN_CENTRE, centre_km=2.0), DEFAULTS) is None


def test_proximity_shows_up_in_the_breakdown_and_raises_the_value():
    housing = snapshot_price("Bursa")
    fields = dict(area_m2=5000.0, usage="tarla", housing=housing, deed="tam", road="var", utilities="var")

    near = estimate(urban=urban(VILLAGE, centre_km=2.0), **fields)
    far = estimate(urban=urban(VILLAGE, centre_km=40.0), **fields)

    assert near.total > far.total
    assert any(factor.key == "centre" for factor in near.factors)


@pytest.mark.parametrize("class_code", [URBAN_CENTRE, TOWN])
def test_city_parcels_have_no_proximity_row(class_code):
    housing = snapshot_price("Bursa")
    result = estimate(area_m2=1000.0, usage="konut", housing=housing, urban=urban(class_code), kaks=1.0)
    assert not any(factor.key == "centre" for factor in result.factors)
