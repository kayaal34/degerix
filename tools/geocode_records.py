"""
Kalibrasyon kayıtlarında boş kalan lat/lng sütunlarını mahalle/köy adından doldurur.

    python tools/geocode_records.py data/private/ilanlar.csv

İlan liste sayfalarında ada/parsel olmaz; konum mahalle ya da köy merkezi olarak bulunur
ve konum sütununa "mahalle" yazılır. Parselin kendisi bilinirse (ada/parsel ya da ilandaki
harita iğnesi) lat/lng elle girilip konum sütununa "parsel" yazılmalıdır.

Mahallesi olmayan kayıtlara dokunulmaz: ilçe merkezinin koordinatı köydeki bir tarlayı
şehir merkezinde gösterir ve kalibrasyonu bozar.

OpenStreetMap Nominatim kullanım politikası gereği saniyede en fazla bir istek atılır.
"""

import csv
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.data import fold  # noqa: E402
from app.nominatim import BASE_URL, USER_AGENT  # noqa: E402

INTERVAL_S = 1.1


def queries(row: dict[str, str]) -> list[str]:
    mahalle, ilce, il = (row.get(key, "").strip() for key in ("mahalle", "ilce", "il"))
    district = "" if ilce == "Merkez" else ilce
    place = ", ".join(part for part in (district, il, "Türkiye") if part)
    return [f"{mahalle}, {place}", f"{mahalle} Mahallesi, {place}"]


def locate(client: httpx.Client, row: dict[str, str]) -> tuple[float, float] | None:
    ilce = row.get("ilce", "").strip()
    for query in queries(row):
        time.sleep(INTERVAL_S)
        response = client.get("/search", params={"q": query, "format": "jsonv2", "limit": 3, "countrycodes": "tr"})
        response.raise_for_status()
        for result in response.json():
            # Aynı adlı köy başka ilçede de olabilir; sonuç doğru ilçede mi?
            if ilce and ilce != "Merkez" and fold(ilce) not in fold(result.get("display_name", "")):
                continue
            return round(float(result["lat"]), 5), round(float(result["lon"]), 5)
    return None


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for column in ("lat", "lng", "konum"):
        if column not in fields:
            fields.append(column)

    found = missing = 0
    with httpx.Client(base_url=BASE_URL, headers={"User-Agent": USER_AGENT, "Accept-Language": "tr"}, timeout=15) as client:
        for row in rows:
            if row.get("lat") or not (row.get("mahalle") or "").strip():
                continue
            point = locate(client, row)
            label = f"{row['il']} / {row['ilce']} / {row['mahalle']}"
            if point is None:
                missing += 1
                print(f"  bulunamadı: {label}")
                continue
            row["lat"], row["lng"] = (str(value) for value in point)
            row["konum"] = "mahalle"
            found += 1
            print(f"  {label}: {point[0]}, {point[1]}")

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{found} kayıt konumlandı, {missing} bulunamadı → {path}")


if __name__ == "__main__":
    main()
