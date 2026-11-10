import asyncio
import pytest
from tools import enrich_auction_locations as collector


def test_exact_names_do_not_guess():
    assert collector.exact_id([{'id': 1, 'name': 'Karıncalı'}], 'Karıncalı Mah.') == 1
    with pytest.raises(ValueError):
        collector.exact_id([{'id': 1, 'name': 'Üçyüzevler'}], '300 Evler')


def test_area_mismatch_does_not_export_coordinates(monkeypatch):
    async def places(*args):
        return [{'id': 1, 'name': 'Bursa'}]
    async def parcel(*args):
        return {'properties': {'alan': '900'}, 'geometry': {'type': 'Polygon',
            'coordinates': [[[29, 40], [29.01, 40], [29.01, 40.01], [29, 40]]]}}
    async def noop(*args):
        pass
    for name in ('list_provinces', 'list_districts', 'list_neighborhoods'):
        monkeypatch.setattr(collector.tkgm, name, places)
    monkeypatch.setattr(collector.tkgm, 'parcel_by_number', parcel)
    monkeypatch.setattr(collector.tkgm, 'close', noop)
    monkeypatch.setattr(collector.asyncio, 'sleep', noop)
    row = dict(il='Bursa', ilce='Bursa', mahalle='Bursa', ada='1', parsel='2', alan_m2='100')
    result = asyncio.run(collector.enrich([row]))[0]
    assert result['lat'] == result['lng'] == ''
    assert 'uyuşmuyor' in result['konum_durumu']
