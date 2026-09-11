import pytest

from app import urbanity

# Ağ erişimi yok: bu testler yalnızca app/static_data altındaki hazır dosyaları okur.
KADIKOY = (40.9900, 29.0300)
MUDANYA = (40.3752, 28.8838)
ASAGIKOCLU = (41.5719, 35.5110)      # Samsun Alaçam'da bir köy parseli
PARIS = (48.8566, 2.3522)


def test_city_centre_is_recognised():
    place = urbanity.describe(*KADIKOY)

    assert place.class_code == urbanity.URBAN_CENTRE
    assert place.label == "şehir merkezi"
    assert place.density > 3000
    assert place.is_rural is False
    assert place.province_centre.name == "İstanbul"  # GeoNames "Istanbul" yazar, Türkçeye çevrilir
    assert place.province_centre.distance_km < 25


def test_village_parcel_is_recognised_as_rural():
    place = urbanity.describe(*ASAGIKOCLU)

    assert place.is_rural is True
    assert place.class_code in (urbanity.VERY_LOW_RURAL, urbanity.LOW_RURAL)
    assert place.density < 100
    assert place.settlement.name == "Aşağıkoçlu"
    assert place.settlement.distance_km < 1.5
    # En yakın merkezler idari değil coğrafidir: parsel Samsun Alaçam'a bağlı olsa da
    # en yakın kasaba Yakakent, en yakın il merkezi Sinop olabilir. Model için önemli
    # olan uzaklıktır; parselin gerçek il/ilçesi TKGM kaydından gelir.
    assert place.district_centre.code == "PPLA2"
    assert place.district_centre.distance_km < 15
    assert place.province_centre.code in urbanity.PROVINCE_CENTRE_CODES
    assert place.province_centre.name in {"Samsun", "Sinop"}
    assert 40 < place.province_centre.distance_km < 120


def test_small_coastal_town_is_between_city_and_village():
    place = urbanity.describe(*MUDANYA)

    assert urbanity.SUBURBAN <= place.class_code <= urbanity.URBAN_CENTRE
    assert place.is_rural is False
    assert place.district_centre.name == "Mudanya"


def test_nearby_class_is_at_least_the_cell_class():
    for point in (KADIKOY, MUDANYA, ASAGIKOCLU):
        place = urbanity.describe(*point)
        assert place.nearby_class >= place.class_code


def test_outside_turkey_returns_none():
    assert urbanity.describe(*PARIS) is None


def test_every_class_has_a_label():
    header, classes, _ = urbanity._grid()
    assert header["format"] == "degerix-urbanity-1"
    assert set(classes) <= set(urbanity.CLASS_LABELS)


def test_results_are_cached():
    assert urbanity.describe(*MUDANYA) is urbanity.describe(*MUDANYA)


@pytest.mark.parametrize("codes", [urbanity.PROVINCE_CENTRE_CODES, urbanity.DISTRICT_CENTRE_CODES])
def test_centre_search_returns_matching_codes(codes):
    place = urbanity._nearest(*MUDANYA, codes=codes, max_km=200)
    assert place is not None and place.code in codes
