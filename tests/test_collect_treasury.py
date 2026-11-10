from tools.collect_treasury import extract


def test_treasury_does_not_invent_area_or_sale_price():
    cells = ['Arsa', '', 'Hayır', 'Konya', 'Yunak', 'Köy', '-', '1.684.000,00', 'Detay']
    rows = extract('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
    assert rows[0]['deger_tl'] == 1684000
    assert rows[0]['alan_m2'] == ''
    assert rows[0]['deger_turu'] != 'satis'


def test_detail_url_stays_with_its_row():
    cells = ['Tarla', '', 'Hayır', 'Konya', 'Yunak', 'Köy', '-', '167.000,00',
             '<a href="?detay=bilgisi&amp;sf=0&amp;index=6">Detay</a>']
    row = extract('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')[0]
    assert 'index=6' in row['detay_url']
    assert row['ilce'] == 'Yunak'
