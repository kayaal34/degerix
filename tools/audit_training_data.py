"""İnceleme CSV'lerini tarar; eğitim engellerini JSON olarak raporlar."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from tools.calibrate import valid_record


def audit(paths):
    total, eligible = 0, 0
    issues, sources = Counter(), Counter()
    for path in paths:
        with path.open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                total += 1
                sources[str(path.name)] += 1
                sale = row.get('deger_turu') == 'satis'
                if not sale:
                    issues['gerceklesen_satis_degil'] += 1
                for field in ('lat', 'lng', 'imar', 'tarih', 'alan_m2', 'deger_tl', 'ada', 'parsel'):
                    if not row.get(field):
                        issues[f'eksik_{field}'] += 1
                identity = all(row.get(k) for k in ('il', 'ilce', 'mahalle', 'ada', 'parsel'))
                eligible += bool(sale and identity and valid_record(row))
    return dict(toplam=total, egitim_adayi=eligible, kaynaklar=dict(sources),
                engeller=dict(issues), notlar='Engel sayıları örtüşebilir; aday sayısı bağımsız parsel sayısı değildir.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
