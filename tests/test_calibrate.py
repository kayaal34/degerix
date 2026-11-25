"""Kalibrasyonun gerçek kayıtlara nasıl tepki verdiği.

Buradaki asıl soru şudur: az sayıda ve tek bölgeden gelen kayıt, ülke geneli
katsayıları ne kadar savurabilmeli? Cevap "çok az" olmalı.
"""

import math

import pytest

from app import urbanity
from app.model_params import DEFAULTS
from tools.calibrate import (
    FITTED,
    MIN_RECORDS_PER_CLASS,
    PROVINCE_TARGET,
    confidence,
    evaluate,
    fit_one,
    is_unzoned,
)

RURAL = urbanity.LOW_RURAL


def rows(count: int, ratio: float, provinces: tuple[str, ...] = ("Bursa",), usage: str = "tarla"):
    """Modelin `ratio` katı düşük tahmin ettiği `count` adet kayıt."""
    # Beşinci alan modelin kullandığı yöntem; fit_one bakmaz ama evaluate üretir
    return [
        ({"il": provinces[index % len(provinces)], "imar": usage}, ratio, 1.0, RURAL, "arazi")
        for index in range(count)
    ]


@pytest.mark.parametrize(
    ("usage", "unzoned"),
    [("tarla", True), ("zeytinlik", True), ("bag_bahce", True),
     ("konut", False), ("ticari", False), ("sanayi", False)],
)
def test_usage_is_routed_to_the_right_coefficient(usage, unzoned):
    assert is_unzoned({"imar": usage}) is unzoned


def test_confidence_grows_with_records_and_provinces():
    few = confidence([0.0] * 5, {"Bursa"})
    many = confidence([0.0] * 50, {"Bursa"})
    spread = confidence([0.0] * 50, {f"İl{index}" for index in range(PROVINCE_TARGET)})

    assert 0 < few < many < spread <= 1
    assert spread == pytest.approx(50 / 60, rel=0.01)   # tek eksik kalan: kayıt sayısı


def test_one_region_cannot_move_a_nationwide_coefficient_far():
    """14 Marmara kaydı tarla oranını üç katına çıkarmaya yetmemeli."""
    fitted = fit_one(rows(14, ratio=5.0), DEFAULTS, "farmland_ratio")

    prior = DEFAULTS.farmland_ratio[RURAL]
    assert prior < fitted[RURAL] < prior * 2


def test_the_same_deviation_across_many_provinces_counts_more():
    one_region = fit_one(rows(14, 5.0, ("Bursa",)), DEFAULTS, "farmland_ratio")
    nationwide = fit_one(rows(14, 5.0, ("Bursa", "Konya", "Erzurum", "Aydın", "Adana")), DEFAULTS, "farmland_ratio")

    assert nationwide[RURAL] > one_region[RURAL]


def test_adjustment_is_capped_even_with_overwhelming_data():
    plenty = rows(500, ratio=50.0, provinces=tuple(f"İl{index}" for index in range(20)))
    fitted = fit_one(plenty, DEFAULTS, "farmland_ratio")

    assert fitted[RURAL] == pytest.approx(DEFAULTS.farmland_ratio[RURAL] * FITTED["farmland_ratio"])


def test_a_handful_of_records_is_ignored_entirely():
    fitted = fit_one(rows(MIN_RECORDS_PER_CLASS - 1, ratio=5.0), DEFAULTS, "farmland_ratio")

    assert fitted == DEFAULTS.farmland_ratio


def test_farmland_records_do_not_disturb_the_locality_coefficient():
    """Tarla kayıtları yalnızca arazi oranını besler; imarlı arsa katsayısı korunur."""
    farmland = rows(20, ratio=5.0, usage="tarla")
    zoned = [row for row in farmland if not is_unzoned(row[0])]

    assert fit_one(zoned, DEFAULTS, "locality") == DEFAULTS.locality


def test_an_accurate_model_is_left_alone():
    fitted = fit_one(rows(30, ratio=1.0), DEFAULTS, "farmland_ratio")

    assert fitted[RURAL] == pytest.approx(DEFAULTS.farmland_ratio[RURAL], rel=0.01)


def test_fitting_moves_toward_the_data_not_past_it():
    """Düzeltme ölçülen sapmanın yönünde ve onu aşmadan olmalı."""
    for ratio in (0.25, 4.0):
        fitted = fit_one(rows(20, ratio, tuple(f"İl{i}" for i in range(5))), DEFAULTS, "farmland_ratio")
        movement = fitted[RURAL] / DEFAULTS.farmland_ratio[RURAL]

        assert 1 < movement <= ratio if ratio > 1 else ratio <= movement < 1


def test_calibration_file_round_trips_both_coefficients():
    """calibration.json yazılıp okunduğunda iki katsayı da modele ulaşmalı."""
    from app.model_params import _merge

    overrides = {
        "locality": {str(RURAL): 0.5},
        "farmland_ratio": {str(RURAL): 0.02},
    }
    merged = _merge(DEFAULTS, overrides)

    assert merged.locality[RURAL] == 0.5
    assert merged.farmland_ratio[RURAL] == 0.02
    assert merged.locality[urbanity.URBAN_CENTRE] == DEFAULTS.locality[urbanity.URBAN_CENTRE]


def test_shrinkage_is_a_geometric_pull_toward_the_default():
    """Büzülme log uzayında olmalı: yarı güvende düzeltme karekök kadar uygulanır."""
    ratios = [math.log(4.0)] * 10
    weight = confidence(ratios, {"Bursa", "Konya"})
    fitted = fit_one(rows(10, 4.0, ("Bursa", "Konya")), DEFAULTS, "farmland_ratio")

    assert fitted[RURAL] == pytest.approx(DEFAULTS.farmland_ratio[RURAL] * 4.0 ** weight, rel=0.01)


def test_deviation_is_charged_to_the_class_the_model_actually_used():
    """Sapma, katsayının okunduğu sınıfa yazılmalı: hücrenin ham sınıfına değil.

    Erişilebilirlik sınıfı eklendiğinden beri fiyat seviyesi, parselin kendi
    hücresi ile çevresinden devraldığı sınıfın kentsel olanından okunuyor.
    Kalibrasyon ham hücre sınıfını kullandığı sürece Diyarbakır/Kayapınar şehir
    merkezi oranıyla fiyatlanırken düzeltme seyrek kırsala gidiyor, yani her
    geçişte yanlış katsayı oynuyordu.
    """
    import asyncio

    from app import urbanity as u
    from app.valuation import effective_class

    kayit = {
        "il": "Diyarbakır", "imar": "tarla", "alan_m2": "472", "deger_tl": "3150000",
        "deger_turu": "ilan", "lat": "37.93173267", "lng": "40.06970652", "_kaynak": "test",
    }
    yer = u.describe(float(kayit["lat"]), float(kayit["lng"]))
    assert yer is not None
    # Testin anlamı bu noktanın iki sınıfının farklı olmasına bağlı
    assert yer.class_code != effective_class(yer)

    satirlar = asyncio.run(evaluate([kayit], DEFAULTS))
    assert satirlar, "kayıt değerlendirilemedi"
    assert satirlar[0][3] == effective_class(yer)


@pytest.mark.anyio
async def test_fit_never_returns_a_worse_set_than_the_defaults(monkeypatch):
    """Yazılan katsayı, ölçülmüş en iyi adaydır; "son geçiş" değil.

    Fit tek yönlü yakınsamıyor: locality hem imarlı hem imarsız kayıtları
    kaydırdığı için ölçüm 96,8 → 66,8 → 78,2 diye salınabiliyor. Eskiden döngü
    son geçişin katsayısını döndürüp bir önceki geçişin raporunu yazıyordu, yani
    dosyaya giren sayı ile ölçülen sayı aynı duruma ait değildi. Hiçbir geçiş
    varsayılanı geçemiyorsa varsayılan kalmalı.
    """
    import tools.calibrate as kalibrasyon

    sabit = rows(8, 1.5) + rows(8, 1.5, usage="konut")

    async def degismez(records, parameters):
        return sabit            # katsayı ne olursa olsun aynı sapma

    monkeypatch.setattr(kalibrasyon, "evaluate", degismez)
    fitted, summary = await kalibrasyon.fit([{}], DEFAULTS)

    assert fitted is DEFAULTS
    assert summary["ortanca_sapma_yuzde"] == pytest.approx(50.0, abs=0.1)
