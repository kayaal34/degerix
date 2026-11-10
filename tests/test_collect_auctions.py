import pytest
from tools.collect_auctions import extract


def document(price="300.000 TL", deposit="9.000 TL"):
    return '<table>' + ''.join(
        '<tr>' + ''.join(f'<td>{cell}</td>' for cell in
        [i, 'Karıncalı Mah.', 'ARSA', '115', i, '122,23', 'TAM', price, deposit]) + '</tr>'
        for i in range(1, 10)) + '</table>'


def test_valid_amount_and_no_invented_features():
    rows = extract(document())
    assert len(rows) == 9
    assert rows[0]['deger_tl'] == 300000
    assert rows[0]['alan_m2'] == 122.23
    assert rows[0]['deger_turu'] == 'muhammen'
    assert rows[0]['lat'] == rows[0]['imar'] == rows[0]['tarih'] == ''


def test_ambiguous_amount_is_quarantined():
    assert extract(document('2.500,000TL', '75.000 TL'))[0]['deger_tl'] == ''


def test_deposit_mismatch_is_quarantined():
    assert extract(document(deposit='90.000 TL'))[0]['deger_tl'] == ''


def test_changed_source_fails_closed():
    with pytest.raises(ValueError):
        extract('<table></table>')
