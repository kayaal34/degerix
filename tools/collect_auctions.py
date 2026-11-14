"""Orhaneli toplu ihale tablosunu inceleme CSV'sine aktarır (eğitime otomatik girmez)."""
import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.tkgm import parse_area

URL = "https://www.bursavar.com/haber/28605618/orhaneli-belediyesi-tasinmaz-satis-ilani"


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag in ("td", "th"):
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            if self.row is not None:
                self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def extract(html):
    parser = Tables()
    parser.feed(html)
    records, seen = [], set()
    for cells in parser.rows:
        if len(cells) != 9 or not cells[0].isdigit() or cells[2].upper() != "ARSA":
            continue
        _, neighborhood, _, block, parcel, area, share, price, deposit = cells
        amount = lambda value: parse_area(re.sub(r"[^\d.,]", "", value))
        value, size, security = amount(price), amount(area), amount(deposit)
        # Bu kaynakta 2.500,000 gibi bozuk fiyatlar var: tahmin etme, incelemeye bırak.
        ambiguous = bool(re.search(r"[.,]\d{3}[.,]\d{3}", price))
        key = (neighborhood, block, parcel)
        if key in seen:
            continue
        seen.add(key)
        valid = value and size and security and abs(security / value - .03) < .001 and not ambiguous
        records.append(dict(il="Bursa", ilce="Orhaneli", mahalle=neighborhood,
                            ada=block, parsel=parcel, alan_m2=size or "",
                            deger_tl=value if valid else "", deger_turu="muhammen",
                            tarih="", ihale_tarihi="2026-09-15", lat="", lng="", imar="",
                            kaynak_url=URL, kaynak_turu="belediye_ihale",
                            ham_bedel=price, durum="konum_imar_tarih_dogrulanmali" if valid else "bedel_dogrulanmali"))
    if len(records) != 9:
        raise ValueError(f"Kaynak biçimi değişmiş olabilir: 9 yerine {len(records)} kayıt")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, help="İndirme yerine yerel kaynak HTML")
    parser.add_argument("--output", type=Path, default=ROOT / "data/source/orhaneli_review.csv")
    args = parser.parse_args()
    raw = args.html.read_bytes() if args.html else urlopen(
        Request(URL, headers={"User-Agent": "Degerix-research/1.0"}), timeout=30).read()
    records = extract(raw.decode("utf-8-sig"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    args.output.with_suffix(".metadata.json").write_text(json.dumps({
        "url": URL, "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(raw).hexdigest(), "records": len(records),
        "training_ready": False,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(records)} inceleme kaydı: {args.output}")


if __name__ == "__main__":
    main()
