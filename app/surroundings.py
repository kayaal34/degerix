"""
Parselin çevresine göre katsayılar: denize ve ana yola mesafe, yakındaki hizmetler, eğim.

Saf fonksiyonlardır; ölçümler app/nearby.py'de OpenStreetMap ve yükselti servisinden
alınır. Etkiler bilinçli olarak dar tutulur: ilçe katsayısı bölgenin ortalamasını
zaten taşır, bunlar aynı ilçe içindeki farkı ayırt eder.
"""

import math
from dataclasses import dataclass

COAST_RADIUS_M = 3000
MAIN_ROAD_RADIUS_M = 1500
SERVICES_RADIUS_M = 1000


@dataclass(frozen=True)
class OsmContext:
    coast_m: float | None       # None: COAST_RADIUS_M içinde kıyı yok
    main_road_m: float | None   # None: MAIN_ROAD_RADIUS_M içinde ana yol yok
    services: int               # SERVICES_RADIUS_M içindeki okul, sağlık ve market noktası


@dataclass(frozen=True)
class Surroundings:
    osm: OsmContext | None      # None: OpenStreetMap'e ulaşılamadı
    slope_pct: float | None     # None: yükselti alınamadı


def coast_multiplier(distance_m: float | None) -> float:
    """Kıyıda 1,20; 500 m'de ~1,10; 3 km'de etkisiz."""
    if distance_m is None:
        return 1.0
    return 1 + 0.20 * math.exp(-distance_m / 700)


def main_road_multiplier(distance_m: float | None) -> float:
    """Ana yola 150 m içinde 1,05; 800 m'ye kadar nötr; daha uzakta 0,95; 1,5 km içinde yoksa 0,90."""
    if distance_m is None:
        return 0.90
    if distance_m <= 150:
        return 1.05
    if distance_m <= 800:
        return 1.0
    return 0.95


def services_multiplier(count: int) -> float:
    """1 km içinde hiç hizmet noktası yoksa 0,95; 12 ve üzerinde 1,05."""
    return 0.95 + 0.10 * min(count, 12) / 12


def slope_multiplier(slope_pct: float) -> float:
    """%5'e kadar düz sayılır; %25 ve üzeri eğimde 0,85."""
    return 1.0 - 0.15 * min(max(slope_pct - 5, 0.0), 20.0) / 20


def _distance(meters: float) -> str:
    if meters < 1000:
        return f"{round(meters / 10) * 10:.0f} m"
    return f"{meters / 1000:.1f} km".replace(".", ",")


def factor_rows(surroundings: Surroundings) -> list[tuple[str, str, float, str]]:
    """Değerleme dökümüne eklenecek (anahtar, etiket, katsayı, açıklama) satırları; ölçülemeyenler atlanır."""
    rows = []
    osm = surroundings.osm
    if osm is not None:
        rows.append((
            "coast", "Denize yakınlık", round(coast_multiplier(osm.coast_m), 3),
            f"Kıyıya {_distance(osm.coast_m)}" if osm.coast_m is not None else "3 km içinde kıyı yok",
        ))
        rows.append((
            "main_road", "Ana yola erişim", main_road_multiplier(osm.main_road_m),
            f"Ana yola {_distance(osm.main_road_m)}" if osm.main_road_m is not None else "1,5 km içinde ana yol yok",
        ))
        rows.append((
            "services", "Çevre hizmetleri", round(services_multiplier(osm.services), 3),
            f"1 km içinde {osm.services} okul, sağlık ya da market noktası",
        ))
    if surroundings.slope_pct is not None:
        rows.append((
            "slope", "Eğim", round(slope_multiplier(surroundings.slope_pct), 3),
            f"Yaklaşık %{surroundings.slope_pct:.0f}",
        ))
    return rows
