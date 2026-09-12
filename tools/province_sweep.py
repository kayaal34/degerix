"""
81 ilin merkezinde aynı parseli hesaplar ve uç değerleri işaretler.

    python tools/province_sweep.py

Her il merkezinde 1.000 m², konut imarlı, emsal 1,00, müstakil tapulu, yola cepheli
bir parsel varsayılır. Amaç mutlak doğruluk değil; bir ilde modelin saçmalayıp
saçmalamadığını görmek. Konut fiyatı depodaki TCMB kopyasından okunur (ağ gerekmez).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import urbanity  # noqa: E402
from app.evds_series import SALES_SERIES  # noqa: E402
from app.market import snapshot_price  # noqa: E402
from app.valuation import estimate  # noqa: E402

ANSWERS = dict(deed="tam", road="var", utilities="var", view="yok")

# GeoNames'te merkezin adı ille aynı değilse
CENTRE_NAMES = {"Hatay": "Antakya", "Kocaeli": "İzmit", "Sakarya": "Adapazarı"}


def province_centres() -> dict[str, tuple[float, float]]:
    """GeoNames'teki il merkezleri (PPLA/PPLC)."""
    centres = {}
    for bucket in urbanity._settlements().values():
        for name, lat, lng, code, _ in bucket:
            if code in urbanity.PROVINCE_CENTRE_CODES:
                centres[name] = (lat, lng)
    return centres


def main() -> int:
    centres = province_centres()
    rows, missing = [], []

    for province in sorted(SALES_SERIES):
        point = centres.get(CENTRE_NAMES.get(province, province))
        if point is None:
            missing.append(province)
            continue
        housing = snapshot_price(province)
        context = urbanity.describe(*point)
        result = estimate(area_m2=1000.0, usage="konut", housing=housing, urban=context, kaks=1.0, **ANSWERS)
        rows.append((result.unit_price, province, context.label, result.basis, housing.value, housing.estimated))

    rows.sort(reverse=True)
    print(f"{'il':<16}{'yerleşim':<22}{'yöntem':<12}{'konut TL/m²':>12}{'arsa TL/m²':>12}")
    print("-" * 74)
    for unit_price, province, settlement, basis, housing_price, estimated in rows:
        mark = " *" if estimated else ""
        print(f"{province:<16}{settlement:<22}{basis:<12}{housing_price:>12,}{unit_price:>12,}{mark}")

    prices = [row[0] for row in rows]
    print(f"\n{len(rows)} il · en yüksek {max(prices):,} · en düşük {min(prices):,} · "
          f"ortanca {sorted(prices)[len(prices) // 2]:,} TL/m²")
    print("* TCMB o il için konut fiyatı yayımlamıyor, bölge ortalaması kullanıldı")

    problems = []
    if missing:
        problems.append(f"il merkezi bulunamayan: {', '.join(missing)}")
    for unit_price, province, settlement, basis, *_ in rows:
        if unit_price < 200:
            problems.append(f"{province}: şehir merkezinde {unit_price:,} TL/m² fazla düşük")
        if basis == "taban" and settlement == "şehir merkezi":
            problems.append(f"{province}: şehir merkezinde geliştirme hesabı değer bırakmıyor")
    if problems:
        print("\nincelenecek:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nuç değer yok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
