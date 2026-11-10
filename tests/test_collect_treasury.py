from tools.collect_treasury import extract


def test_treasury_does_not_invent_area_or_sale_price():
    cells = ['Arsa', '', 'Hayır', 'Konya', 'Yunak', 'Köy', '-', '1.684.000,00', 'Detay']
    rows = extract('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
    assert rows[0]['deger_tl'] == 1684000
    assert rows[0]['alan_m2'] == ''
    assert rows[0]['deger_turu'] != 'satis'
