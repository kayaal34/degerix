"""Sessizce yanlış cevap veren yolların testleri.

Buradaki her test, ölçümü ya da kullanıcıya gösterilen değeri bozan ama
hiçbir hata vermeyen bir davranışı yakalar. Hepsi incelemede bulundu.
"""

import math

import pytest
from fastapi.testclient import TestClient

from app import nearby
from app.main import app
from tools.olcum_ortak import hedef_tl, yarim_kat_icinde
from tools.toplu_degerle import BelirsizSayi, alan_oku


# ---------- Overpass hatayı 200 ile döndürüyor ----------

def test_overpass_hata_govdesi_olcum_sayilmaz():
    """remark alanı olan yanıt "0 bina, kıyı yok" diye okunmamalı.

    Okunursa imar beklentisi primi sessizce düşer ve yanlış sonuç önbellekte
    24 saat kalır: aynı parsel bir yüklemede 3,4 milyon, diğerinde 6,8 çıkar.
    """
    govde = {"version": 0.6, "remark": "runtime error: Query timed out", "elements": []}
    with pytest.raises(nearby.OverpassRemark):
        nearby.parse_overpass(govde, 40.0, 29.0)


def test_overpass_elements_yoksa_olcum_sayilmaz():
    with pytest.raises(nearby.OverpassRemark):
        nearby.parse_overpass({"version": 0.6}, 40.0, 29.0)


def test_overpass_gercekten_bos_yanit_gecerlidir():
    """Kırın ortasında hiçbir şey bulunmaması geçerli bir ölçümdür.

    Ama "hiçbir şey yok" sıfır değerli bir sayım satırıyla gelir: sorgu
    "out count;" ile bitiyor, yani eksiksiz yanıt her zaman o satırı taşır.
    """
    bos = {"elements": [{"type": "count", "tags": {"ways": "0"}}]}
    bag = nearby.parse_overpass(bos, 40.0, 29.0)
    assert bag.buildings == 0 and bag.coast_m is None


def test_overpass_sayim_satirsiz_yanit_olcum_sayilmaz():
    """Sayım satırı yoksa yanıt yarım kesilmiştir, "0 bina" değil.

    Bu ayrım imar beklentisi primini belirliyor: 400 m içindeki bina sayısı
    sıfır okunursa prim düşer ve parsel iki kat ucuz görünür.
    """
    with pytest.raises(nearby.OverpassRemark):
        nearby.parse_overpass({"elements": []}, 40.0, 29.0)


def test_onbellek_sinirsiz_buyumez():
    nearby.clear_cache()
    try:
        simdi = 1000.0
        for i in range(nearby.CACHE_MAX + 50):
            nearby._cache[f"k{i}"] = (simdi + 10, nearby.Surroundings(osm=None, slope_pct=None))
        nearby._prune_cache(simdi)
        assert len(nearby._cache) <= nearby.CACHE_MAX
    finally:
        nearby.clear_cache()


def test_onbellek_suresi_gecenleri_atar():
    nearby.clear_cache()
    try:
        nearby._cache["eski"] = (5.0, nearby.Surroundings(osm=None, slope_pct=None))
        nearby._cache["yeni"] = (500.0, nearby.Surroundings(osm=None, slope_pct=None))
        nearby._prune_cache(100.0)
        assert "eski" not in nearby._cache and "yeni" in nearby._cache
    finally:
        nearby.clear_cache()


# ---------- Tek koordinat ----------

def test_yalniz_enlem_kabul_edilmez():
    """Yalnız lat gönderilince konuma bağlı her şey sessizce atlanıyordu."""
    istemci = TestClient(app)
    yanit = istemci.post("/api/estimate", json={
        "province": "Bursa", "area_m2": 1000, "usage": "tarla", "lat": 40.0})
    assert yanit.status_code == 422


# ---------- Alan ayrıştırması ----------

@pytest.mark.parametrize("metin, beklenen", [
    ("1.234,5", 1234.5),      # iki ayraç: nokta binlik, virgül ondalık
    ("55,5", 55.5),           # yalnız virgül: Türkçe ondalık
    ("1.000.000", 1_000_000), # birden çok nokta: binlik
    ("55.5", 55.5),           # tek nokta, 3 haneden farklı kesir: ondalık
    ("1234", 1234),
])
def test_alan_okunur(metin, beklenen):
    assert alan_oku(metin) == pytest.approx(beklenen)


@pytest.mark.parametrize("metin", ["10.000", "1.234"])
def test_belirsiz_alan_tahmin_edilmez(metin):
    """10 m² mi 10.000 m² mi belli değilse durmalı.

    Eski kod noktayı silip 10.000'i 10000 yapıyordu; sonraki düzeltme ise
    ondalık sayıp 10,0 yaptı — bin kat hata. İkisi de sessizdi.
    """
    with pytest.raises(BelirsizSayi):
        alan_oku(metin)


# ---------- Ölçüm tanımları ----------

def test_yarim_kat_carpimsal_ve_simetrik():
    """İki kat şişirmek ile yarıya düşürmek aynı büyüklükte hatadır."""
    assert yarim_kat_icinde(1.0)
    assert yarim_kat_icinde(1.5) and yarim_kat_icinde(1 / 1.5)
    assert not yarim_kat_icinde(1.51) and not yarim_kat_icinde(1 / 1.51)
    # Eski toplamsal tanım 0,5'i içeride sayıyordu; çarpımsal saymaz
    assert not yarim_kat_icinde(0.5)
    # log ekseninde simetri
    for oran in (0.4, 0.6, 0.9, 1.1, 1.8, 2.5):
        assert yarim_kat_icinde(oran) == yarim_kat_icinde(1 / oran), oran


def test_gerceklesen_satisa_pazarlik_payi_uygulanmaz():
    assert hedef_tl(100.0, "satis", 0.12) == 100.0
    assert hedef_tl(100.0, "ilan", 0.12) == pytest.approx(88.0)


def test_bilinmeyen_deger_turu_varsayilmaz():
    """Sessizce ilan ya da satış saymak ölçümü gizlice bozar."""
    assert hedef_tl(100.0, "", 0.12) is None
    assert hedef_tl(100.0, "muhammen", 0.12) is None
    assert hedef_tl(100.0, None, 0.12) is None
