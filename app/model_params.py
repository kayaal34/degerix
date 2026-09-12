"""
Değerleme modelinin ayarlanabilir katsayıları.

Buradaki değerler başlangıç varsayımıdır. tools/calibrate.py gerçek kayıtlarla
(Bursa pilot seti ve elle derlenen doğrulama verisi) katsayıları ayarlayıp
app/static_data/calibration.json dosyasına yazar; dosya varsa değerler oradan okunur.
Böylece hangi sayının varsayım, hangisinin veriyle ayarlandığı görünür kalır.

Yerleşim sınıfı kodları app/urbanity.py ile aynıdır.
"""

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .urbanity import (
    DENSE_CLUSTER,
    EMPTY,
    LOW_RURAL,
    SUBURBAN,
    TOWN,
    URBAN_CENTRE,
    VERY_LOW_RURAL,
    VILLAGE,
)

CALIBRATION_FILE = Path(__file__).resolve().parent / "static_data" / "calibration.json"


def _by_class(urban_centre: float, dense: float, town: float, suburban: float,
              village: float, low_rural: float, very_low_rural: float) -> dict[int, float]:
    return {
        URBAN_CENTRE: urban_centre,
        DENSE_CLUSTER: dense,
        TOWN: town,
        SUBURBAN: suburban,
        VILLAGE: village,
        LOW_RURAL: low_rural,
        VERY_LOW_RURAL: very_low_rural,
        EMPTY: very_low_rural,
    }


@dataclass(frozen=True)
class Parameters:
    """Modelin veriyle ayarlanabilen tüm sayıları."""

    # İl geneli konut fiyatını parselin yerleşimine indirger (il ortalaması = 1,00).
    # TCMB'nin il fiyatı ağırlıklı olarak şehir merkezini yansıttığı için kırsalda düşer.
    locality: dict[int, float] = field(default_factory=lambda: _by_class(1.05, 0.85, 0.70, 0.80, 0.50, 0.42, 0.36))

    # Emsal (KAKS) bilinmiyorsa yerleşime göre varsayılan inşaat hakkı
    default_kaks: dict[int, float] = field(default_factory=lambda: _by_class(1.50, 1.20, 0.90, 1.00, 0.50, 0.35, 0.30))

    # Geliştirme hesabı arsaya değer bırakmadığında taban: konut m² fiyatının oranı
    floor_ratio: dict[int, float] = field(default_factory=lambda: _by_class(0.100, 0.080, 0.050, 0.060, 0.030, 0.020, 0.018))

    # İmarsız arazide arsa değeri: konut m² fiyatının oranı
    farmland_ratio: dict[int, float] = field(default_factory=lambda: _by_class(0.030, 0.020, 0.015, 0.020, 0.012, 0.008, 0.006))

    # Brüt inşaat alanının satılabilir kısmı (ortak alanlar düşülür)
    sellable_ratio: float = 0.80

    # Müteahhidin riski ve finansman yükü; hasılatın oranı olarak düşülür.
    # Bakanlık birim maliyetleri zaten %15 genel gider ve %10 yüklenici kârı içeriyor.
    developer_margin: float = 0.15

    # Konut dışı kullanımlarda satış fiyatı farkı (konut = 1,00)
    usage_price_ratio: dict[str, float] = field(default_factory=lambda: {"konut": 1.00, "ticari": 1.25, "sanayi": 0.55})

    # İmarsız arazide kullanım farkı (tarla = 1,00)
    farmland_usage_ratio: dict[str, float] = field(default_factory=lambda: {"tarla": 1.00, "bag_bahce": 1.40, "zeytinlik": 1.60})

    # İlan fiyatı ile gerçekleşen satış arasındaki tipik pazarlık payı.
    # Yalnızca kalibrasyonda kullanılır: ilan fiyatları bu oranda indirilerek karşılaştırılır.
    asking_discount: float = 0.12

    # Kullanıcının girdiği emsallerin sonuca etkisi: her emsal için ağırlık ve üst sınır.
    # Model tamamen devre dışı kalmaz; birkaç emsal yanlışsa sonucu tek başına belirlemesin.
    comparable_weight_per_record: float = 0.20
    comparable_weight_cap: float = 0.60

    source: str = "varsayılan"


DEFAULTS = Parameters()


def _merge(defaults: Parameters, overrides: dict) -> Parameters:
    """calibration.json içindeki alanları varsayılanların üzerine yazar."""
    values = {}
    for name, current in vars(defaults).items():
        override = overrides.get(name)
        if override is None:
            values[name] = current
        elif isinstance(current, dict):
            keys_are_numbers = all(isinstance(key, int) for key in current)
            merged = dict(current)
            for key, value in override.items():
                merged[int(key) if keys_are_numbers else key] = value
            values[name] = merged
        else:
            values[name] = override
    return Parameters(**values)


@lru_cache(maxsize=1)
def load() -> Parameters:
    """Kalibrasyon dosyası varsa onunla, yoksa varsayılanlarla."""
    if not CALIBRATION_FILE.exists():
        return DEFAULTS
    data = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
    overrides = data.get("parametreler", {})
    merged = _merge(DEFAULTS, overrides)
    return Parameters(**(vars(merged) | {"source": data.get("kaynak", "kalibrasyon")}))


def reload() -> Parameters:
    """Kalibrasyon dosyası değiştiğinde önbelleği tazeler (testler ve betikler için)."""
    load.cache_clear()
    return load()
