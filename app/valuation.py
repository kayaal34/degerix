"""
Arsa değer tahmini.

Yalnızca saf fonksiyonlardan oluşur: ağ, veritabanı ya da rastgelelik yoktur.
Aynı girdi her zaman aynı sonucu verir ve her çarpan gerekçesiyle birlikte
döndürülür; böylece arayüz hesabın nasıl yapıldığını adım adım gösterebilir.

    m² fiyatı = il referans fiyatı   (konut imarlı, emsal 1,00, yola cepheli arsa)
              × ilçe katsayısı       (bilinen ilçeler için bölge farkı)
              × konum katsayısı      (ilçenin coğrafi merkezine uzaklık)
              × çevre katsayıları    (denize ve ana yola mesafe, hizmetler, eğim)
              × imar katsayısı       (konut / ticari / sanayi imarlı ya da imarsız)
              × emsal katsayısı      (KAKS; yalnızca imarlı arsada)
              × büyüklük katsayısı   (büyük parselde m² fiyatı düşer)
              × tapu, yol cephesi, elektrik-su katsayıları

"Bilmiyorum" denen sorular değeri değiştirmez ama değer aralığını genişletir;
kullanıcı yanıtladıkça aralık daralır ve güven düzeyi yükselir. Sonuç, satış
süresine göre üç senaryo (acil satış, piyasa değeri, tok satıcı) olarak da verilir.
"""

import math
import re
from dataclasses import dataclass

from .data import (
    DEED,
    DEFAULT_BASE_PRICE,
    REFERENCE_KAKS,
    ROAD,
    SALE_SCENARIOS,
    UNKNOWN,
    USAGE,
    UTILITIES,
    district_factor,
    fold,
    province_base_price,
)
from .geo import haversine_km
from .surroundings import Surroundings, factor_rows

RURAL_USAGES = frozenset({"tarla", "bag_bahce", "zeytinlik"})

# Sıra önemli: "Kargir Dükkan ve Arsa" ticari sayılmalı, "Kargir Ev ve Bahçe" konut.
_USAGE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("ticari", ("dukkan", "magaza", "otel", "akaryakit", "ticari", "isyeri")),
    ("sanayi", ("fabrika", "sanayi", "atolye", "imalathane")),
    ("konut", ("arsa", "bina", "ev", "konut", "kargir", "ahsap", "apartman", "mesken", "villa")),
    ("zeytinlik", ("zeytin",)),
    ("bag_bahce", ("bag", "bahce", "meyve", "findik", "narenciye")),
    ("tarla", ("tarla", "mera", "cayir", "arazi", "toprak")),
]


@dataclass(frozen=True)
class DistrictArea:
    """İlçenin coğrafi merkezi ve yüzölçümü (TKGM ilçe sınırından hesaplanır)."""

    lat: float
    lng: float
    area_km2: float

    @property
    def radius_km(self) -> float:
        """Aynı alana sahip dairenin yarıçapı; çok küçük ilçelerde 1,5 km'de sabitlenir."""
        return max(1.5, math.sqrt(self.area_km2 / math.pi))


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    multiplier: float
    detail: str


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    timeframe: str
    value: int
    low: int
    high: int


@dataclass(frozen=True)
class Estimate:
    base_price: int
    unit_price: int
    total: int
    low: int
    high: int
    confidence: str
    factors: list[Factor]
    scenarios: list[Scenario]
    share_pct: float | None = None    # hisseli tapuda kullanıcının payı
    share_value: int | None = None    # o paya düşen değer


def location_multiplier(distance_km: float, radius_km: float) -> float:
    """Merkezde 1,10; bir yarıçap uzakta ~0,93; çok uzakta 0,85'e yaklaşır.

    İlçenin coğrafi merkezi her zaman şehir merkezi olmadığından (ör. Kızılay,
    Çankaya'nın coğrafi merkezine ~12 km uzakta) etki bilinçli olarak dar tutulur.
    """
    return 0.85 + 0.25 * math.exp(-1.2 * distance_km / radius_km)


def size_multiplier(area_m2: float) -> float:
    """500 m² referans alınır; 5.000 m²'de ~0,85, 50.000 m²'de ~0,72."""
    return min(1.08, max(0.65, (area_m2 / 500) ** -0.07))


def kaks_multiplier(kaks: float) -> float:
    """Emsal 1,00 referans alınır. İnşaat hakkı arttıkça değer artar ama orantısız:
    0,50 → ~0,66 · 2,00 → ~1,52; 0,50–1,80 bandında sınırlanır."""
    return min(1.8, max(0.5, (kaks / REFERENCE_KAKS) ** 0.6))


def nice_round(value: float, digits: int = 3) -> int:
    """Sahte hassasiyet vermemek için anlamlı basamağa yuvarlar (57.432.100 → 57.400.000)."""
    if value <= 0:
        return 0
    step = 10 ** max(0, math.floor(math.log10(value)) + 1 - digits)
    return int(round(value / step) * step)


def guess_usage(nitelik: str | None) -> str:
    """TKGM nitelik metninden imar durumu önerisi; kullanıcı arayüzde değiştirebilir."""
    tokens = re.findall(r"[a-z]+", fold(nitelik or ""))
    for usage, keywords in _USAGE_KEYWORDS:
        for keyword in keywords:
            if any(token == keyword or (len(keyword) >= 4 and token.startswith(keyword)) for token in tokens):
                return usage
    return "konut"


def _thousands(value: float) -> str:
    return f"{round(value):,}".replace(",", ".")


def _decimal(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def estimate(
    *,
    province: str,
    district: str,
    area_m2: float,
    usage: str,
    lat: float | None = None,
    lng: float | None = None,
    district_area: DistrictArea | None = None,
    surroundings: Surroundings | None = None,
    kaks: float | None = None,
    deed: str = UNKNOWN,
    share_pct: float | None = None,
    road: str = UNKNOWN,
    utilities: str = UNKNOWN,
) -> Estimate:
    if area_m2 <= 0:
        raise ValueError("Alan sıfırdan büyük olmalı.")
    if usage not in USAGE:
        raise ValueError(f"Bilinmeyen imar durumu: {usage}")
    if kaks is not None and kaks <= 0:
        raise ValueError("Emsal sıfırdan büyük olmalı.")
    if share_pct is not None and not 0 < share_pct <= 100:
        raise ValueError("Hisse payı 0 ile 100 arasında olmalı.")
    for name, answer, options in (("tapu", deed, DEED), ("yol cephesi", road, ROAD), ("elektrik-su", utilities, UTILITIES)):
        if answer != UNKNOWN and answer not in options:
            raise ValueError(f"Geçersiz {name} yanıtı: {answer}")

    spread = 0.08  # değer aralığının yarı genişliği; her eksik bilgi büyütür
    factors: list[Factor] = []

    base_price = province_base_price(province)
    if base_price is None:
        base_price = DEFAULT_BASE_PRICE
        spread += 0.08

    known_district = district_factor(province, district)
    if known_district is None:
        factors.append(Factor("district", "İlçe", 1.0, f"{district} için ayrı katsayı yok, il ortalaması"))
        spread += 0.05
    else:
        factors.append(Factor("district", "İlçe", known_district, f"{district} bölge farkı"))

    if district_area is not None and lat is not None and lng is not None:
        distance = haversine_km(lat, lng, district_area.lat, district_area.lng)
        factors.append(Factor(
            "location", "Konum",
            round(location_multiplier(distance, district_area.radius_km), 3),
            f"İlçenin coğrafi merkezine {distance:.1f} km".replace(".", ","),
        ))
    else:
        factors.append(Factor("location", "Konum", 1.0, "İlçe sınırı alınamadı, konum etkisi yok"))
        spread += 0.04

    if surroundings is not None:
        factors.extend(Factor(*row) for row in factor_rows(surroundings))

    zoned = usage not in RURAL_USAGES
    usage_label, usage_multiplier = USAGE[usage]
    factors.append(Factor("usage", "İmar durumu", usage_multiplier, usage_label))
    if not zoned:
        spread += 0.06

    if zoned:  # imarsız arazide emsal sorulmaz
        if kaks is None:
            factors.append(Factor("kaks", "Emsal (KAKS)", 1.0, f"Girilmedi, {_decimal(REFERENCE_KAKS)} varsayıldı"))
            spread += 0.04
        else:
            factors.append(Factor(
                "kaks", "Emsal (KAKS)",
                round(kaks_multiplier(kaks), 3),
                f"{_decimal(kaks)} → {_thousands(area_m2 * kaks)} m² inşaat hakkı",
            ))

    factors.append(Factor("size", "Büyüklük", round(size_multiplier(area_m2), 3), f"{_thousands(area_m2)} m² parsel"))

    utility_options = {
        key: (label, zoned_multiplier if zoned else rural_multiplier)
        for key, (label, zoned_multiplier, rural_multiplier) in UTILITIES.items()
    }
    for key, label, answer, options in (
        ("deed", "Tapu", deed, DEED),
        ("road", "Yol cephesi", road, ROAD),
        ("utilities", "Elektrik ve su", utilities, utility_options),
    ):
        if answer == UNKNOWN:
            factors.append(Factor(key, label, 1.0, "Yanıtlanmadı, aralık genişletildi"))
            spread += 0.02
        else:
            detail, multiplier = options[answer]
            factors.append(Factor(key, label, multiplier, detail))
    if deed == "hisseli":
        spread += 0.04

    unit_price = nice_round(base_price * math.prod(factor.multiplier for factor in factors))
    total = unit_price * area_m2

    if spread <= 0.12 + 1e-9:
        confidence = "yüksek"
    elif spread <= 0.22 + 1e-9:
        confidence = "orta"
    else:
        confidence = "düşük"

    scenarios = []
    for key, label, timeframe, zoned_multiplier, rural_multiplier in SALE_SCENARIOS:
        value = total * (zoned_multiplier if zoned else rural_multiplier)
        scenarios.append(Scenario(
            key=key, label=label, timeframe=timeframe,
            value=nice_round(value),
            low=nice_round(value * (1 - spread)),
            high=nice_round(value * (1 + spread)),
        ))

    has_share = deed == "hisseli" and share_pct is not None
    return Estimate(
        base_price=base_price,
        unit_price=unit_price,
        total=nice_round(total),
        low=nice_round(total * (1 - spread)),
        high=nice_round(total * (1 + spread)),
        confidence=confidence,
        factors=factors,
        scenarios=scenarios,
        share_pct=share_pct if has_share else None,
        share_value=nice_round(total * share_pct / 100) if has_share else None,
    )
