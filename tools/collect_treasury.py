"""e-Devlet kamuya açık Hazine ihale listesini inceleme CSV'sine indirir."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from tools.collect_auctions import Tables
from app.tkgm import parse_area

URL = 'https://www.turkiye.gov.tr/csb-tasinmaz-satis-ilanlari-ihaleye-cikanlar?sf=0'
OUTPUT = Path(__file__).resolve().parents[1] / 'data/source/treasury_review.csv'


def extract(html):
    parser = Tables()
    parser.feed(html)
    records = []
    for cells in parser.rows:
        if len(cells) != 9 or cells[0] not in ('Arsa', 'Arazi', 'Tarla', 'Bağ-Bahçe'):
            continue
        kind, _, zoning, province, district, neighborhood, area, price, _ = cells
        records.append(dict(il=province, ilce=district, mahalle=neighborhood,
                            nitelik=kind, kaynak_imar=zoning, alan_m2=parse_area(area) or '',
                            deger_tl=parse_area(price) or '', deger_turu='ihale_ilan_fiyati',
                            lat='', lng='', imar='', tarih='', kaynak_url=URL,
                            durum='detay_ve_fiyat_turu_dogrulanmali'))
    if not records:
        raise ValueError('Kamuya açık tabloda kayıt bulunamadı; çıktı yazılmadı')
    return records


def main():
    raw = urlopen(Request(URL, headers={'User-Agent': 'Degerix-research/1.0'}), timeout=30).read()
    rows = extract(raw.decode('utf-8-sig'))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    OUTPUT.with_suffix('.metadata.json').write_text(json.dumps(dict(
        url=URL, retrieved_at=datetime.now(timezone.utc).isoformat(),
        sha256=hashlib.sha256(raw).hexdigest(), records=len(rows), training_ready=False,
        scope='Yalnızca kamuya açık ilk sayfa; tüm envanter değildir'), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(rows)} Hazine ihale inceleme kaydı')


if __name__ == '__main__':
    main()
