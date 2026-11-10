import asyncio
from dataclasses import replace
from tools import calibrate
from app.model_params import DEFAULTS


def test_parcel_split_prevents_leakage_and_is_order_independent():
    rows = [dict(il='Bursa', ilce='X', mahalle='Y', ada='1', parsel=str(i)) for i in range(100)]
    train, validation = calibrate.split_records(rows + rows)
    assert {r['parsel'] for r in train}.isdisjoint({r['parsel'] for r in validation})
    assert validation and train
    assert {r['parsel'] for r in validation} == {r['parsel'] for r in calibrate.split_records(list(reversed(rows)))[1]}


def test_final_report_measures_returned_parameters(monkeypatch):
    code = next(iter(DEFAULTS.locality))
    seen = []
    async def evaluate(records, parameters):
        seen.append(parameters)
        return [({}, 100, 50, code)] * 5
    monkeypatch.setattr(calibrate, 'evaluate', evaluate)
    fitted, summary = asyncio.run(calibrate.fit([], DEFAULTS))
    assert seen[-1] == fitted
    assert len(seen) == calibrate.PASSES + 1


def test_percentage_metric_uses_target_denominator():
    assert calibrate.report([({}, 100, 76, 10)])['yuzde_25_icinde'] == 100


def test_invalid_records_are_not_silently_treated_as_housing():
    row = dict(lat='40', lng='29', alan_m2='100', deger_tl='100000',
               tarih='2026-09-01', kaynak_url='https://example.org', imar='konut')
    assert calibrate.valid_record(row)
    assert not calibrate.valid_record(row | {'imar': ''})
    assert not calibrate.valid_record(row | {'deger_tl': 'nan'})
    assert not calibrate.valid_record(row | {'tarih': ''})
