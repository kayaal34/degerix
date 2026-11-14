"""İnceleme CSV'sinde kesin idari ad eşleşmesiyle TKGM koordinatı tamamlar."""
import argparse
import asyncio
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import tkgm
from app.geo import centroid_and_area
from app.errors import NotFound, UpstreamError


def normalize(name):
    name = name.translate(str.maketrans('İI', 'ii')).lower().strip()
    return re.sub(r'\s+mah(?:allesi)?\.?$', '', name).strip()


def exact_id(places, name):
    hits = [p['id'] for p in places if normalize(p['name']) == normalize(name)]
    if len(hits) != 1:
        raise ValueError(f'Kesin ve tekil ad eşleşmesi yok: {name}')
    return hits[0]


async def enrich(rows):
    try:
        provinces = await tkgm.list_provinces()
        for row in rows:
            row['lat'] = row['lng'] = ''
            try:
                province = exact_id(provinces, row['il'])
                district = exact_id(await tkgm.list_districts(province), row['ilce'])
                neighborhood = exact_id(await tkgm.list_neighborhoods(district), row['mahalle'])
                feature = await tkgm.parcel_by_number(neighborhood, row['ada'], row['parsel'])
                lat, lng, area = centroid_and_area(feature['geometry'])
                if not area > 0 or not (35 <= lat <= 43 and 25 <= lng <= 45):
                    raise ValueError('Geometri geçersiz')
                official_area = tkgm.parse_area(feature['properties'].get('alan'))
                source_area = float(row['alan_m2'])
                if official_area is None or abs(official_area / source_area - 1) > .05:
                    raise ValueError('TKGM alanı eksik veya kaynakla uyuşmuyor')
                row.update(lat=f'{lat:.7f}', lng=f'{lng:.7f}', konum_durumu='tkgm_eslesti')
            except (ValueError, KeyError, TypeError, NotFound, UpstreamError) as exc:
                row['konum_durumu'] = str(exc)
            await asyncio.sleep(1)
    finally:
        await tkgm.close()
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Kaynağı korumak için farklı çıktı dosyası kullanın')
    with args.input.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        parser.error('CSV boş')
    rows = asyncio.run(enrich(rows))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{sum(bool(r['lat']) for r in rows)}/{len(rows)} konum eşleşti")


if __name__ == '__main__':
    main()
