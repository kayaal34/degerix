"""
Kullanıcının girdiği emsallerin hesaba katılması.

Emsaller sunucuda saklanmaz; yalnızca o hesap için gönderilir ve sonuca ağırlıklı
olarak yansır. İlan fiyatından pazarlık payı düşülür, büyüklük farkı düzeltilir.
"""

import pytest

from app.market import snapshot_price
from app.model_params import DEFAULTS
from app.valuation import Comparable, adjusted_comparable_price, estimate
from app import urbanity

NILUFER = (40.2140, 28.9157)
BASE = dict(area_m2=1000.0, usage="konut", kaks=1.0, deed="tam", road="var", utilities="var", view="yok")


def value(**overrides):
    housing = snapshot_price("Bursa")
    context = urbanity.describe(*NILUFER)
    return estimate(housing=housing, urban=context, **(BASE | overrides))


def factor(result, key):
    return next((f for f in result.factors if f.key == key), None)


def test_listing_price_is_discounted_but_sale_price_is_not():
    listing = adjusted_comparable_price(Comparable(price_tl=1_000_000, area_m2=1000, kind="ilan"), 1000, DEFAULTS)
    sale = adjusted_comparable_price(Comparable(price_tl=1_000_000, area_m2=1000, kind="satis"), 1000, DEFAULTS)
    assert sale == pytest.approx(1000)
    assert listing == pytest.approx(1000 * (1 - DEFAULTS.asking_discount))


def test_large_comparable_is_carried_to_the_subject_scale():
    # 10.000 m²'lik emsalin m² fiyatı 1.000 m²'lik parsele doğrudan uygulanmaz
    adjusted = adjusted_comparable_price(Comparable(price_tl=10_000_000, area_m2=10_000, kind="satis"), 1000, DEFAULTS)
    assert adjusted > 1000


def test_comparables_pull_the_estimate_towards_the_market():
    plain = value()
    cheap = value(comparables=[Comparable(price_tl=2_000_000, area_m2=1000, kind="satis")])

    assert cheap.unit_price < plain.unit_price          # emsal modelin altında
    assert cheap.unit_price > 2000                      # ama model tamamen devre dışı kalmadı
    assert cheap.comparables.count == 1
    assert cheap.comparables.model_unit_price == pytest.approx(plain.unit_price, rel=0.02)


def test_more_comparables_carry_more_weight():
    one = value(comparables=[Comparable(price_tl=2_000_000, area_m2=1000, kind="satis")])
    three = value(comparables=[Comparable(price_tl=2_000_000, area_m2=1000, kind="satis")] * 3)

    assert three.comparables.weight > one.comparables.weight
    assert three.comparables.weight <= DEFAULTS.comparable_weight_cap
    assert three.unit_price < one.unit_price            # piyasaya daha yakın


def test_agreeing_comparables_narrow_the_range_and_scattered_ones_widen_it():
    agreeing = value(comparables=[
        Comparable(price_tl=6_000_000, area_m2=1000, kind="satis"),
        Comparable(price_tl=6_300_000, area_m2=1000, kind="satis"),
    ])
    scattered = value(comparables=[
        Comparable(price_tl=2_000_000, area_m2=1000, kind="satis"),
        Comparable(price_tl=12_000_000, area_m2=1000, kind="satis"),
    ])

    def width(result):
        return (result.high - result.low) / result.total

    assert width(agreeing) < width(scattered)
    assert agreeing.comparables.spread_pct < scattered.comparables.spread_pct


def test_breakdown_shows_the_comparable_row():
    result = value(comparables=[Comparable(price_tl=3_000_000, area_m2=1000, kind="ilan", label="Sahibinden 1")])
    row = factor(result, "comparables")
    assert row is not None
    assert "emsalin ortancası" in row.detail
    assert row.multiplier < 1  # emsal modelin altında kaldığı için değeri aşağı çekti


def test_without_comparables_nothing_changes():
    result = value()
    assert result.comparables is None
    assert factor(result, "comparables") is None


@pytest.mark.parametrize("bad", [
    Comparable(price_tl=0, area_m2=1000),
    Comparable(price_tl=1_000_000, area_m2=0),
    Comparable(price_tl=1_000_000, area_m2=1000, kind="tahmin"),
])
def test_invalid_comparables_are_rejected(bad):
    with pytest.raises(ValueError):
        value(comparables=[bad])
