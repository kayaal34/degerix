"""
Yerleşim listesi üretir: GeoNames Türkiye verisinden il merkezleri, ilçe merkezleri,
beldeler ve köyler çıkarılır.

    python tools/build_settlements.py

Girdi : data/source/geonames_TR.zip  (yoksa indirilir, ~3,6 MB)
Çıktı : app/static_data/settlements_tr.csv.gz

Yalnızca veri hazırlarken çalıştırılır.

Kaynak: GeoNames (geonames.org), lisans: Creative Commons Attribution 4.0.
Özellik kodları: PPLC başkent, PPLA il merkezi, PPLA2 ilçe merkezi,
PPLA3 belde/mahalle, PPL yerleşim (köy dahil), PPLX şehrin bir kesimi.
"""

import csv
import gzip
import io
import sys
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.data import fold  # noqa: E402
from app.evds_series import SALES_SERIES  # noqa: E402

SOURCE = ROOT / "data" / "source" / "geonames_TR.zip"
OUTPUT = ROOT / "app" / "static_data" / "settlements_tr.csv.gz"
SOURCE_URL = "https://download.geonames.org/export/dump/TR.zip"

KEPT_CODES = {"PPLC", "PPLA", "PPLA2", "PPLA3", "PPL", "PPLX"}

# Yalnızca il merkezlerinin adı düzeltilir
PROVINCE_CODES = {"PPLC", "PPLA"}

# 81 ilin resmî yazımı (EVDS seri tablosundaki adlar)
OFFICIAL_PROVINCES = {fold(name): name for name in SALES_SERIES}


def download_source() -> None:
    if SOURCE.exists():
        return
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    print(f"GeoNames verisi indiriliyor: {SOURCE_URL}")
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        response = client.get(SOURCE_URL)
        response.raise_for_status()
    SOURCE.write_bytes(response.content)
    print(f"  {SOURCE.stat().st_size / 1e6:.1f} MB indirildi")


def turkish_name(name: str, code: str) -> str:
    """GeoNames il merkezlerini bazen ASCII yazar ("Istanbul").

    Yalnızca il merkezleri düzeltilir ve düzeltme resmî il adları listesinden yapılır.
    GeoNames'in alternatif adlarına güvenilmiyor: aynı ada denk gelen alternatifler
    bile yanlış olabiliyor ("Kilis" → "Kılis", "Sinop" → "Sînop").
    """
    if code not in PROVINCE_CODES:
        return name
    return OFFICIAL_PROVINCES.get(fold(name), name)


def read_settlements() -> tuple[list[dict[str, str]], list[tuple[str, str]]]:
    rows: list[dict[str, str]] = []
    corrections: list[tuple[str, str]] = []
    with zipfile.ZipFile(SOURCE) as archive, archive.open("TR.txt") as handle:
        for line in io.TextIOWrapper(handle, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 15 or parts[6] != "P" or parts[7] not in KEPT_CODES:
                continue
            name = turkish_name(parts[1], parts[7])
            if name != parts[1]:
                corrections.append((parts[1], name))
            rows.append({
                "name": name,
                "lat": f"{float(parts[4]):.5f}",
                "lng": f"{float(parts[5]):.5f}",
                "code": parts[7],
                "province_code": parts[10],
                "population": parts[14] or "0",
            })
    return rows, corrections


def main() -> None:
    download_source()
    rows, corrections = read_settlements()
    rows.sort(key=lambda row: (row["code"], row["name"]))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["name", "lat", "lng", "code", "province_code", "population"],
        lineterminator="\n",
    )
    writer.writerow({field: field for field in writer.fieldnames})
    writer.writerows(rows)
    OUTPUT.write_bytes(gzip.compress(buffer.getvalue().encode("utf-8"), 9))

    counts = Counter(row["code"] for row in rows)
    with_population = sum(1 for row in rows if int(row["population"]) > 0)
    print(f"yazıldı: {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size / 1e6:.2f} MB) · {date.today().isoformat()}")
    print(f"  toplam {len(rows):,} yerleşim · nüfusu bilinen {with_population:,}")
    for code, count in counts.most_common():
        print(f"  {code:<6} {count:>7,}")
    print(f"  Türkçe yazıma çevrilen ad: {len(corrections):,}")
    for original, corrected in corrections[:8]:
        print(f"    {original} → {corrected}")


if __name__ == "__main__":
    main()
