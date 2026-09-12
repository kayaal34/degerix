"""
Modelin akıl sağlığı kontrolü: etiketli veri olmadan saçma sonuçları yakalar.

    python tools/sanity_check.py

Türkiye'nin farklı yerleşim sınıflarından örnek noktalarda modeli çalıştırır ve
beklenen sıralamaları doğrular:

  - Aynı il ve aynı özelliklerde: şehir merkezi > çeper > kasaba > köy > kırsal
  - Aynı noktada: konut imarlı arsa > tarla
  - Emsal (KAKS) arttıkça değer artar
  - Büyük parselde m² fiyatı düşer
  - Değer aralığı tahmini kapsar, hiçbir değer sıfır ya da negatif değil

Bir kural bozulursa çıkış kodu 1 olur; sürekli entegrasyona bağlanabilir.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app import market, urbanity  # noqa: E402
from app.valuation import estimate  # noqa: E402

# Aynı il içinde farklı yerleşim sınıfları: konut fiyatı sabit kalır, fark yalnızca yerleşimden gelir
SAMPLES = [
    ("Bursa", "Nilüfer merkez", 40.2140, 28.9157),
    ("Bursa", "Mudanya", 40.3752, 28.8838),
    ("Bursa", "Karacabey", 40.2136, 28.3600),
    ("Bursa", "Kestel çeperi", 40.1980, 29.2100),
    ("Bursa", "Gölyazı", 40.1690, 28.6820),
    ("Bursa", "kırsal (Keles yolu)", 39.9800, 29.2400),
    ("İstanbul", "Şişli", 41.0602, 28.9877),
    ("Samsun", "Alaçam merkez", 41.6056, 35.5981),
    ("Samsun", "Aşağıkoçlu köyü", 41.5719, 35.5110),
]

ANSWERS = dict(deed="tam", road="var", utilities="var", view="yok")
AREA = 1000.0


async def run() -> int:
    prices = {}
    for province, *_ in SAMPLES:
        if province not in prices:
            prices[province] = await market.housing_price(province)

    print(f"{'yer':<24}{'yerleşim sınıfı':<22}{'yöntem':<12}{'TL/m²':>10}{'toplam':>16}")
    print("-" * 84)

    results = []
    for province, label, lat, lng in SAMPLES:
        context = urbanity.describe(lat, lng)
        housing = prices[province]
        konut = estimate(area_m2=AREA, usage="konut", housing=housing, urban=context, kaks=1.0, **ANSWERS)
        tarla = estimate(area_m2=AREA, usage="tarla", housing=housing, urban=context, **ANSWERS)
        results.append((province, label, context, konut, tarla))
        print(f"{label:<24}{context.label:<22}{konut.basis:<12}{konut.unit_price:>10,}{konut.total:>16,}")

    failures = []

    # 1. Aynı il içinde kentsellik sıralaması
    for province in {sample[0] for sample in SAMPLES}:
        in_province = [row for row in results if row[0] == province]
        ordered = sorted(in_province, key=lambda row: row[2].class_code, reverse=True)
        for higher, lower in zip(ordered, ordered[1:]):
            if higher[2].class_code == lower[2].class_code:
                continue
            if higher[3].unit_price < lower[3].unit_price:
                failures.append(
                    f"{province}: {higher[1]} ({higher[2].label}) {higher[3].unit_price:,} TL/m² < "
                    f"{lower[1]} ({lower[2].label}) {lower[3].unit_price:,} TL/m²"
                )

    # 2. Konut imarlı arsa tarladan pahalı
    for province, label, context, konut, tarla in results:
        if konut.unit_price <= tarla.unit_price:
            failures.append(f"{label}: konut {konut.unit_price:,} ≤ tarla {tarla.unit_price:,} TL/m²")

    # 3. Emsal arttıkça değer artar · 4. büyük parselde m² fiyatı düşer · 5. aralık tutarlı
    province, label, context, konut, _ = results[0]
    housing = prices[province]
    low_kaks = estimate(area_m2=AREA, usage="konut", housing=housing, urban=context, kaks=0.5, **ANSWERS)
    high_kaks = estimate(area_m2=AREA, usage="konut", housing=housing, urban=context, kaks=2.0, **ANSWERS)
    if not low_kaks.unit_price < konut.unit_price < high_kaks.unit_price:
        failures.append(f"{label}: emsal arttıkça değer artmıyor "
                        f"({low_kaks.unit_price:,} / {konut.unit_price:,} / {high_kaks.unit_price:,})")

    large = estimate(area_m2=20_000, usage="konut", housing=housing, urban=context, kaks=1.0, **ANSWERS)
    if large.unit_price >= konut.unit_price:
        failures.append(f"{label}: 20.000 m² parselin m² fiyatı 1.000 m²'den düşük değil")

    for province, label, context, konut, tarla in results:
        for result in (konut, tarla):
            if not (0 < result.low < result.total < result.high):
                failures.append(f"{label}: aralık tutarsız ({result.low:,} / {result.total:,} / {result.high:,})")

    print()
    if failures:
        print(f"{len(failures)} kural bozuldu:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("tüm kurallar geçti")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
