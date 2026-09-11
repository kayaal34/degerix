"""
Konut piyasası verisi: ilin konut m² satış fiyatı.

Öncelik canlı TCMB EVDS'tir. Anahtar tanımlı değilse ya da servise ulaşılamazsa
app/static_data/konut_birim_fiyat.json içindeki kopya kullanılır; bu dosya
tools/build_housing_prices.py ile üretilir.

Dönen fiyat il genelinin ortalamasıdır. Değerleme modeli bunu parselin yerleşim
sınıfına göre yerelleştirir (bkz. app/valuation.py).
"""

import json
from functools import lru_cache
from pathlib import Path

from . import evds
from .data import fold
from .errors import NotFound, UpstreamError
from .valuation import HousingPrice  # tip değerleme modülünde tanımlı, buradan da dışa verilir

SNAPSHOT_FILE = Path(__file__).resolve().parent / "static_data" / "konut_birim_fiyat.json"

__all__ = ["HousingPrice", "housing_price", "snapshot_price"]


@lru_cache(maxsize=1)
def _snapshot() -> dict:
    return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _index() -> dict[str, str]:
    """Türkçe yazım farklarını yok sayan il adı dizini."""
    return {fold(name): name for name in _snapshot()["iller"]}


def snapshot_price(province: str) -> HousingPrice | None:
    """Kopyadaki fiyat; il tanınmazsa None."""
    data = _snapshot()
    name = _index().get(fold(province))
    if name is None:
        return None
    return HousingPrice(
        province=name,
        value=int(data["iller"][name]),
        period=evds.format_period(data["donem"]),
        source=f"TCMB EVDS kopyası ({data['guncelleme']})",
        live=False,
        estimated=name in data["tahmin_edilen"],
    )


async def housing_price(province: str) -> HousingPrice:
    """İlin konut m² fiyatı: önce canlı EVDS, olmazsa kopya."""
    if evds.is_configured():
        try:
            stats = await evds.province_stats(province)
        except (NotFound, UpstreamError):
            stats = None
        if stats is not None and stats.unit_price is not None:
            return HousingPrice(
                province=stats.province,
                value=stats.unit_price.value,
                period=stats.unit_price.period,
                source="TCMB EVDS",
                live=True,
                estimated=False,
            )

    price = snapshot_price(province)
    if price is None:
        raise NotFound(f"{province} için konut fiyatı verisi bulunamadı.")
    return price
