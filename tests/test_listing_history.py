from copy import deepcopy

import pytest

from tools.import_listings import merge


def test_history_reimport_and_out_of_order():
    base = dict(url="https://example.org/1", province="Bursa", district="Nilüfer", title="Arsa")
    early = dict(base, date="2025-01-01", status="Aktif", price="250000")
    late = dict(base, title="Güncel başlık", date="2025-03-01", status="Kaldırıldı", price="")
    offers = merge([], [late, early])
    assert offers[0]["title"] == late["title"]
    assert [e["price"] for e in offers[0]["history"]] == [250000, None]
    assert merge(deepcopy(offers), [early, late]) == offers
    with pytest.raises(ValueError):
        merge(offers, [dict(early, price="2")])

def test_archive_map_fields_are_optional_and_validated():
    base = dict(url="https://example.org/1", province="Bursa", district="Nilüfer", title="Arsa",
                date="2026-01-01", status="Aktif", price="100000")
    offer, = merge([], [dict(base, lat="40.2", lng="29", neighborhood_id="123")])
    assert (offer["lat"], offer["lng"], offer["neighborhoodId"]) == (40.2, 29, 123)
    with pytest.raises(ValueError):
        merge([], [dict(base, lat="40.2")])
