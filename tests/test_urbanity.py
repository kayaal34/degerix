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
    # Skor √nüfus/mesafe² olduğu için yakındaki küçük ilçe merkezi, uzaktaki büyük
    # ilçeyi (18 km'deki Nilüfer, 536 bin) yenebiliyor.
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


MUDARLI = (41.003662, 29.552141)       # Gebze, Kocaeli
CENTRAL_ANATOLIA = (39.0, 34.0)        # Kırşehir civarı, büyükşehirden uzak


def test_strongest_centre_prefers_the_bigger_town():
    place = urbanity.describe(*MUDARLI)

    # Şile daha yakın (~20 km, 20 bin kişi) ama Gebze (~25 km, 281 bin kişi) daha çekici
    assert place.district_centre.name == "Gebze"
    assert place.district_centre.distance_km > 20


def test_metro_is_found_near_istanbul_and_missing_in_the_middle_of_anatolia():
    near = urbanity.describe(*MUDARLI)
    assert near.metro is not None and near.metro.population >= 250_000
    assert near.metro.distance_km < 150

    # İç Anadolu'da eşiği henüz geçen bir il merkezi (Aksaray, 327 bin) bulunabilir.
    # Önemli olan varlığı değil gücü: primin nüfusla ölçeklenmesi onu önemsiz kılar.
    # Çekimin gerçekten sönümlendiğini test_model_sanity'deki çarpan testi doğruluyor.
    far = urbanity.describe(*CENTRAL_ANATOLIA)
    assert far is not None
    assert far.metro is None or far.metro.population < near.metro.population / 10
