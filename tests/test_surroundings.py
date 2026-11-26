import asyncio
import math

import pytest

from app import nearby, urbanity
from app.geo import distance_to_line_m
from app.surroundings import (
    OsmContext,
    Surroundings,
    factor_rows,
    settlement_position,
)
from app.model_params import DEFAULTS
from app.valuation import HousingPrice, estimate

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


def test_distance_to_line():
    line = [(37.001, 27.0), (37.001, 27.02)]
    assert distance_to_line_m(37.0, 27.01, line) == pytest.approx(110.6, rel=0.01)   # çizgiye dik
    assert distance_to_line_m(37.0, 27.03, line) == pytest.approx(895.9, rel=0.01)   # uç noktaya
    assert distance_to_line_m(37.0, 27.01, [(37.0, 27.01)]) == 0
    assert math.isinf(distance_to_line_m(37.0, 27.0, []))


def test_surroundings_are_reported_without_touching_the_value():
    """Kıyı, ana yol, hizmet ve eğim 103 ilanda ölçüldü: fiyat etkisi bulunamadı.
    Ölçüm dökümde kalır (kullanıcı neye bakıldığını görür) ama değeri oynatmaz."""
    measured = Surroundings(osm=OsmContext(coast_m=420, main_road_m=None, services=3), slope_pct=12.4)
    (key, label, multiplier, detail), = factor_rows(measured)

    assert (key, label, multiplier) == ("surroundings", "Çevre ölçümleri", 1.0)
    assert detail == ("Kıyıya 420 m · 1,5 km içinde ana yol yok · 1 km içinde 3 okul, "
                      "sağlık ya da market noktası · eğim yaklaşık %12 · "
                      "103 ilanda fiyat etkisi ölçülemedi")

    arguments = dict(area_m2=800, usage="konut", housing=BURSA, urban=place(urbanity.DENSE_CLUSTER), kaks=1.0)
    plain = estimate(**arguments)
    with_surroundings = estimate(**arguments, surroundings=measured)

    assert "surroundings" in {f.key for f in with_surroundings.factors}
    assert with_surroundings.unit_price == plain.unit_price
    assert (with_surroundings.low, with_surroundings.high) == (plain.low, plain.high)


def test_unavailable_measurements_are_skipped():
    assert factor_rows(Surroundings(osm=None, slope_pct=None)) == []
    rows = factor_rows(Surroundings(osm=None, slope_pct=3.0))
    assert [row[0] for row in rows] == ["surroundings"]
    assert rows[0][3].startswith("Eğim yaklaşık %3")


def test_parse_overpass_classifies_elements():
    data = {"elements": [
        {"type": "way", "tags": {"natural": "coastline"}, "geometry": [{"lat": 40.001, "lon": 28.9}, {"lat": 40.001, "lon": 28.92}]},
        {"type": "way", "tags": {"highway": "primary"}, "geometry": [{"lat": 40.0, "lon": 28.905}, {"lat": 40.0, "lon": 28.915}]},
        {"type": "node", "tags": {"amenity": "school"}},
        {"type": "way", "tags": {"shop": "supermarket"}, "center": {"lat": 40.0, "lon": 28.91}},
        # Sorgu "out count;" ile bitiyor: eksiksiz her yanıtta sayım satırı olur
        {"type": "count", "tags": {"ways": "0"}},
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
        "province": "Muğla", "area_m2": 500, "usage": "konut", "lat": 37.0385, "lng": 27.419,
    }).json()
    cevre, = (f for f in body["factors"] if f["key"] == "surroundings")
    assert cevre["multiplier"] == 1.0 and "Kıyıya 300 m" in cevre["detail"]


def test_fetch_within_does_not_wait_for_slow_services_and_shares_requests(monkeypatch):
    calls = []
    measured = Surroundings(osm=None, slope_pct=2.0)

    async def slow_fetch(lat, lng):
        calls.append((lat, lng))
        await asyncio.sleep(0.2)
        return measured

    monkeypatch.setattr(nearby, "fetch", slow_fetch)

    async def two_estimates_for_same_parcel():
        return await asyncio.gather(
            nearby.fetch_within(40.2, 28.9, budget_s=0.01),
            nearby.fetch_within(40.2, 28.9, budget_s=1.0),
        )

    impatient, patient = asyncio.run(two_estimates_for_same_parcel())
    assert impatient is None        # süre aşıldı, değer beklemeden hesaplanır
    assert patient is measured      # ölçüm iptal edilmedi, arka planda tamamlandı
    assert len(calls) == 1          # eşzamanlı istekler tek ölçümü paylaştı


def test_settlement_position_reads_the_edge_of_a_settlement():
    # Boş kır: ne bina ne çizilmiş yerleşik alan.
    assert settlement_position(OsmContext(coast_m=None, main_road_m=None, services=0)) == "kir"
    # Kıyının ölçütü görünen binadır, çizilmiş sınıra yakınlık değil: 900 m ötede
    # yerleşik alan çizili olsa da yanında hiç bina yoksa parsel kır sayılır.
    assert settlement_position(OsmContext(
        coast_m=None, main_road_m=None, services=0, buildings=4)) == "kiyi"
    assert settlement_position(OsmContext(
        coast_m=None, main_road_m=None, services=0, built_up_m=900)) == "kir"
    # İçi: yoğun bina ya da poligonun içinde olmak.
    assert settlement_position(OsmContext(
        coast_m=None, main_road_m=None, services=0, buildings=240)) == "ic"
    assert settlement_position(OsmContext(
        coast_m=None, main_road_m=None, services=0, buildings=3, built_up_m=0)) == "ic"
    # Ölçüm yoksa karar da yok; prim uydurulmaz.
    assert settlement_position(None) is None


def test_parse_overpass_counts_buildings_and_finds_the_built_up_area():
    data = {"elements": [
        {"type": "way", "tags": {"landuse": "residential"}, "geometry": [
            {"lat": 40.01, "lon": 28.90}, {"lat": 40.01, "lon": 28.92},
            {"lat": 40.02, "lon": 28.92}, {"lat": 40.02, "lon": 28.90}]},
        {"type": "count", "tags": {"ways": "7"}},
    ]}
    osm = nearby.parse_overpass(data, 40.0, 28.91)
    assert osm.buildings == 7
    assert osm.built_up_m == pytest.approx(1112, abs=30)   # poligonun güney kenarına
    assert settlement_position(osm) == "kiyi"           # 7 bina görünüyor

    # Nokta poligonun içindeyse uzaklık sıfırdır ve parsel yerleşimin içi sayılır.
    icteki = nearby.parse_overpass(data, 40.015, 28.91)
    assert icteki.built_up_m == 0
    assert settlement_position(icteki) == "ic"


def _kirsal(lat: float = 40.21, lng: float = 28.62) -> urbanity.Urbanity | None:
    return urbanity.describe(lat, lng)


def test_fringe_premium_lifts_unzoned_land_only_at_the_edge():
    """Ölçülen desen: kırda ve yerleşimin içinde model isabet ediyor, kıyıda şaşıyor."""
    yer = _kirsal()
    assert yer is not None
    ortak = dict(area_m2=3_000, usage="tarla", housing=BURSA, urban=yer)

    kir = Surroundings(osm=OsmContext(coast_m=None, main_road_m=400, services=0,
                                      built_up_m=700), slope_pct=2.0)
    kiyi = Surroundings(osm=OsmContext(coast_m=None, main_road_m=400, services=0,
                                       buildings=6, built_up_m=700), slope_pct=2.0)
    ic = Surroundings(osm=OsmContext(coast_m=None, main_road_m=400, services=0,
                                     buildings=300, built_up_m=0), slope_pct=2.0)

    kirda = estimate(**ortak, surroundings=kir)
    kiyida = estimate(**ortak, surroundings=kiyi)
    icte = estimate(**ortak, surroundings=ic)

    assert "fringe" not in {f.key for f in kirda.factors}
    assert "fringe" not in {f.key for f in icte.factors}
    kiyi_etken = next(f for f in kiyida.factors if f.key == "fringe")
    assert kiyi_etken.multiplier == pytest.approx(DEFAULTS.fringe_premium)
    # Prim yalnızca kıyıda değeri yükseltir; hizmet/yol katsayıları aynı olduğu için
    # iki değerin oranı doğrudan primdir.
    assert kiyida.unit_price / kirda.unit_price == pytest.approx(DEFAULTS.fringe_premium, rel=0.02)


def test_fringe_premium_does_not_touch_zoned_land():
    """İmarlı arsada aynı düzeltme ölçümde hatayı artırıyordu (47 iyi / 57 bozuk)."""
    yer = _kirsal()
    assert yer is not None
    kiyi = Surroundings(osm=OsmContext(coast_m=None, main_road_m=400, services=0,
                                       buildings=6, built_up_m=700), slope_pct=2.0)
    sonuc = estimate(area_m2=3_000, usage="konut", housing=BURSA, urban=yer, surroundings=kiyi)
    assert "fringe" not in {f.key for f in sonuc.factors}


def test_fringe_widens_the_band_as_well_as_the_value():
    """Prim seviyeyi düzeltir, belirsizliği gidermez: ölçümde kıyıda tipik sapma
    primden sonra bile ×2,21, kapı dışında ×1,58."""
    yer = _kirsal()
    assert yer is not None
    ortak = dict(area_m2=3_000, usage="tarla", housing=BURSA, urban=yer)
    kir = Surroundings(osm=OsmContext(coast_m=None, main_road_m=400, services=0,
                                      built_up_m=700), slope_pct=2.0)
    kiyi = Surroundings(osm=OsmContext(coast_m=None, main_road_m=400, services=0,
                                       buildings=6, built_up_m=700), slope_pct=2.0)

    kirda, kiyida = estimate(**ortak, surroundings=kir), estimate(**ortak, surroundings=kiyi)
    genislik = lambda s: (s.high - s.low) / s.total            # noqa: E731
    assert genislik(kiyida) > genislik(kirda)
    # Aralık çarpımsaldır: değer, alt ve üst sınırın ortasında değil, oranların
    # ortasında durur. Alt sınır bu yüzden hiçbir yayılımda sıfıra inemez.
    for sonuc in (kirda, kiyida):
        assert sonuc.low > 0
        assert sonuc.high / sonuc.total == pytest.approx(sonuc.total / sonuc.low, rel=0.02)


def test_cevre_olculemezse_fiyat_ag_hizina_birakilmaz():
    """Ölçülen hata: Overpass yetişmediğinde aynı tarla 2,45 milyon TL, yetiştiğinde
    4,90 milyon TL ediyordu. Artık bilinmezlik banda yazılıyor."""
    yer = _kirsal()
    assert yer is not None
    ortak = dict(area_m2=10_000, usage="tarla", housing=BURSA, urban=yer)
    kiyi = Surroundings(osm=OsmContext(coast_m=None, main_road_m=400, services=0,
                                       buildings=6, built_up_m=700), slope_pct=2.0)

    olculemedi = estimate(**ortak, surroundings=None)
    primli = estimate(**ortak, surroundings=kiyi)

    assert "fringe_unknown" in {f.key for f in olculemedi.factors}
    # Nokta tahmin primsiz kalır (kayıtların çoğunda prim yok) ama aralık
    # primli sonucu kapsar: ağ hızı artık iki kat fark yaratmıyor.
    assert olculemedi.high >= primli.total
    assert olculemedi.low > 0
    # Çevre ölçülemeyince aralık alışılmışın üstüne çıkar ve bunu söyler
    assert olculemedi.confidence == "alışılmıştan geniş"
