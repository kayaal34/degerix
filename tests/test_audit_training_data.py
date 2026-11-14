import csv
from tools.audit_training_data import audit


def test_auction_is_not_training_candidate(tmp_path):
    path = tmp_path / 'review.csv'
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['deger_turu', 'alan_m2'])
        writer.writeheader()
        writer.writerow(dict(deger_turu='muhammen', alan_m2='100'))
    result = audit([path])
    assert result['toplam'] == 1
    assert result['egitim_adayi'] == 0
    assert result['engeller']['gerceklesen_satis_degil'] == 1
    assert result['engeller']['eksik_imar'] == 1
