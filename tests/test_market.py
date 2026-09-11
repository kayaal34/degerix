import asyncio

import pytest

from app import evds, market
from app.errors import NotFound, UpstreamError


@pytest.fixture(autouse=True)
def without_evds_key(monkeypatch):
    """Geliştiricinin .env anahtarı testlere sızmasın; varsayılan olarak kopya kullanılır."""
    monkeypatch.delenv("EVDS_API_KEY", raising=False)


def price_for(province: str) -> market.HousingPrice:
    return asyncio.run(market.housing_price(province))


def test_snapshot_covers_every_province():
    snapshot = market._snapshot()
    assert len(snapshot["iller"]) == 81
    assert all(value > 5_000 for value in snapshot["iller"].values())
    assert snapshot["donem"].endswith(("Q1", "Q2", "Q3", "Q4"))
    # TCMB'nin fiyat yayımlamadığı iller işaretli olmalı
    assert set(snapshot["tahmin_edilen"]) == {"Ardahan", "Bayburt", "Gümüşhane", "Hakkari", "Tunceli"}


def test_snapshot_price_ignores_spelling_differences():
    for spelling in ("Muğla", "MUĞLA", "mugla"):
        price = market.snapshot_price(spelling)
        assert price.province == "Muğla"
        assert price.value > 20_000
        assert price.live is False and price.estimated is False
        assert "çeyrek" in price.period


def test_provinces_without_official_data_are_marked():
    assert market.snapshot_price("Gümüşhane").estimated is True
    assert market.snapshot_price("Atlantis") is None


def test_falls_back_to_snapshot_when_key_is_missing():
    price = price_for("Samsun")
    assert price.live is False
    assert price.source.startswith("TCMB EVDS kopyası")
    assert price.value == market.snapshot_price("Samsun").value


def test_uses_live_evds_when_available(monkeypatch):
    monkeypatch.setenv("EVDS_API_KEY", "test-anahtari")

    async def fake_stats(province):
        return evds.ProvinceStats(
            province="Samsun",
            unit_price=evds.UnitPrice(value=40_000, period="2026 3. çeyrek", change_pct=12.0),
            price_index=None,
            sales=None,
        )

    monkeypatch.setattr(evds, "province_stats", fake_stats)
    price = price_for("Samsun")
    assert (price.live, price.value, price.period, price.source) == (True, 40_000, "2026 3. çeyrek", "TCMB EVDS")


def test_falls_back_to_snapshot_when_evds_is_down(monkeypatch):
    monkeypatch.setenv("EVDS_API_KEY", "test-anahtari")

    async def failing_stats(province):
        raise UpstreamError("TCMB EVDS servisine ulaşılamadı.")

    monkeypatch.setattr(evds, "province_stats", failing_stats)
    price = price_for("Samsun")
    assert price.live is False and price.value == market.snapshot_price("Samsun").value


def test_unknown_province_raises_not_found():
    with pytest.raises(NotFound):
        price_for("Atlantis")
