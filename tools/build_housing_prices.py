"""
İl bazında konut m² fiyatlarının yedek kopyasını üretir.

    python tools/build_housing_prices.py

TCMB EVDS'ten (TP.BIRIMFIYAT) her ilin son dönem konut birim fiyatı çekilir ve
app/static_data/konut_birim_fiyat.json dosyasına yazılır. Uygulama normalde canlı
EVDS'i kullanır; anahtar tanımlı değilse ya da servise ulaşılamazsa bu kopyaya döner.

TCMB'nin birim fiyat yayımlamadığı beş il (Ardahan, Bayburt, Gümüşhane, Hakkari,
Tunceli) için, ilin konut fiyat endeksi bölgesindeki diğer illerin ortalaması yazılır
ve "tahmin_edilen" listesinde işaretlenir.

Çalıştırmak için .env içinde EVDS_API_KEY gerekir.
"""

import asyncio
import json
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app import evds  # noqa: E402
from app.evds_series import PRICE_INDEX_REGIONS, UNIT_PRICE_PREFIX, UNIT_PRICE_SERIES  # noqa: E402

OUTPUT = ROOT / "app" / "static_data" / "konut_birim_fiyat.json"
COUNTRY_SERIES = f"{UNIT_PRICE_PREFIX}TR"
CONCURRENCY = 4


async def latest_value(code: str, start: date, end: date, limiter: asyncio.Semaphore) -> tuple[str, float] | None:
    for attempt in range(3):  # anlık ağ hatasında seri kaybolmasın
        async with limiter:
            try:
                points = await evds.fetch_series(code, start, end)
            except Exception as error:  # noqa: BLE001 — tek seri düşerse diğerleri sürsün
                if attempt == 2:
                    print(f"  {code}: alınamadı ({error})")
                    return None
                await asyncio.sleep(1 + attempt)
                continue
        return points[-1] if points else None
    return None


async def main() -> None:
    load_dotenv(ROOT / ".env")
    if not evds.is_configured():
        sys.exit(".env içinde EVDS_API_KEY tanımlı değil.")

    today = date.today()
    start = date(today.year - 2, 1, 1)
    limiter = asyncio.Semaphore(CONCURRENCY)

    provinces = list(UNIT_PRICE_SERIES.items())
    results = await asyncio.gather(
        *(latest_value(f"{UNIT_PRICE_PREFIX}{code}", start, today, limiter) for _, code in provinces),
        latest_value(COUNTRY_SERIES, start, today, limiter),
    )
    country = results[-1]

    prices: dict[str, int] = {}
    periods: list[str] = []
    for (province, _), result in zip(provinces, results[:-1]):
        if result is None:
            continue
        period, value = result
        prices[province] = round(value)
        periods.append(period)

    # Verisi olmayan iller: kendi konut fiyat endeksi bölgesinin ortalaması
    estimated: list[str] = []
    for region_provinces in PRICE_INDEX_REGIONS.values():
        known = [prices[name] for name in region_provinces if name in prices]
        if not known:
            continue
        for name in region_provinces:
            if name not in prices:
                prices[name] = round(statistics.mean(known))
                estimated.append(name)

    period = statistics.mode(periods) if periods else "bilinmiyor"
    snapshot = {
        "kaynak": "TCMB EVDS · TP.BIRIMFIYAT (konut birim m² fiyatı)",
        "donem": period,
        "guncelleme": today.isoformat(),
        "turkiye": round(country[1]) if country else None,
        "tahmin_edilen": sorted(estimated),
        "iller": dict(sorted(prices.items())),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    values = sorted(prices.values())
    print(f"yazıldı: {OUTPUT.relative_to(ROOT)} · dönem {period} · {len(prices)} il")
    print(f"  Türkiye: {snapshot['turkiye']:,} TL/m²" if snapshot["turkiye"] else "  Türkiye: yok")
    print(f"  en düşük {values[0]:,} · ortanca {statistics.median(values):,.0f} · en yüksek {values[-1]:,} TL/m²")
    print(f"  bölge ortalamasından tamamlanan iller: {', '.join(snapshot['tahmin_edilen']) or 'yok'}")
    for name in ("İstanbul", "Ankara", "İzmir", "Bursa", "Muğla", "Samsun"):
        if name in prices:
            print(f"  {name:<10} {prices[name]:>8,} TL/m²")


if __name__ == "__main__":
    asyncio.run(main())
