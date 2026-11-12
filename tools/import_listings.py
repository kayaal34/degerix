"""İlan gözlemlerini birleştirir: python tools/import_listings.py dosya.csv"""
import argparse
import csv
from datetime import date
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

OUTPUT = Path(__file__).resolve().parents[1] / "static" / "listings.json"


def merge(existing, rows):
    offers = {item["url"]: item for item in existing}
    for line, row in enumerate(rows, start=2):
        try:
            url = row["url"].strip()
            address = urlsplit(url)
            if address.scheme != "https" or not address.hostname or address.username or address.password:
                raise ValueError("Kaynak için HTTPS adresi gerekli")
            details = {key: row[key].strip() for key in ("title", "province", "district")}
            if not all(details.values()):
                raise ValueError("Başlık, il ve ilçe gerekli")
            lat, lng = (row.get("lat") or "").strip(), (row.get("lng") or "").strip()
            if lat or lng:
                if not (lat and lng and 35.5 <= float(lat) <= 42.5 and 25.5 <= float(lng) <= 45):
                    raise ValueError("Geçerli bir enlem ve boylam çifti gerekli")
                details.update(lat=float(lat), lng=float(lng))
            if row.get("neighborhood_id"):
                neighborhood = int(row["neighborhood_id"])
                if neighborhood <= 0:
                    raise ValueError("Geçerli TKGM mahalle kimliği gerekli")
                details["neighborhoodId"] = neighborhood
            day = date.fromisoformat(row["date"].strip()).isoformat()
            status = row["status"].strip()
            if status not in {"Aktif", "Kaldırıldı"}:
                raise ValueError("Durum Aktif veya Kaldırıldı olmalı")
            price = int(row["price"]) if row["price"].strip() else None
            if (price is None and status == "Aktif") or (price is not None and price <= 0):
                raise ValueError("Geçerli TL fiyatı gerekli")
            offer = offers.setdefault(url, dict(url=url, history=[], **details))
            history = {event["date"]: event for event in offer["history"]}
            event = dict(date=day, status=status, price=price)
            if day in history and history[day] != event:
                raise ValueError("Aynı tarihte çelişen gözlem")
            if not history or day >= max(history):
                offer.update(details)
            history[day] = event
            offer["history"] = [history[d] for d in sorted(history)]
        except (KeyError, ValueError, AttributeError) as error:
            raise ValueError(f"Satır {line}: {error}") from error
    return sorted(offers.values(), key=lambda item: item["url"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    args = parser.parse_args()
    with args.csv_file.open(encoding="utf-8-sig", newline="") as source:
        result = merge(json.loads(OUTPUT.read_text(encoding="utf-8")), csv.DictReader(source))
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=OUTPUT.parent, delete=False) as target:
        json.dump(result, target, ensure_ascii=False, indent=2)
        target.write("\n")
    Path(target.name).replace(OUTPUT)


if __name__ == "__main__":
    main()
