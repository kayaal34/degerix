import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from app import evds
from app.data import fold
from app.errors import NotFound, UpstreamError
from app.evds_series import PRICE_INDEX_REGIONS, SALES_SERIES, UNIT_PRICE_SERIES


def monthly(year: int, month: int, values: list[float | None]) -> list[tuple[str, float | None]]:
    points = []
    for value in values:
        points.append((f"{year}-{month}", value))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return points


def response(code: str, points: list[tuple[str, float | None]]) -> dict:
    column = code.replace(".", "_")
    return {
        "totalCount": len(points),
        "items": [{"Tarih": label, column: None if value is None else f"{value:.8f}"} for label, value in points],
    }


MUGLA_UNIT_PRICE = [("2025-Q1", 66547.4), ("2025-Q2", 79077.4), ("2025-Q3", 74391.9),
                    ("2025-Q4", 76618.8), ("2026-Q1", 79109.6), ("2026-Q2", 82290.3)]
TR32_INDEX = monthly(2024, 7, [150 + i for i in range(25)])      # Temmuz 2024 – Temmuz 2026
MUGLA_SALES = monthly(2024, 8, [1000] * 12 + [1100] * 12)        # Ağustos 2024 – Temmuz 2026


@pytest.fixture(autouse=True)
def isolated_evds(monkeypatch):
    """Geliştiricinin .env dosyasındaki gerçek anahtar testlere sızmasın, önbellek taşınmasın."""
    monkeypatch.delenv("EVDS_API_KEY", raising=False)
    evds.clear_cache()
    yield
    evds.clear_cache()


@pytest.fixture
def fake_evds(monkeypatch):
    monkeypatch.setenv("EVDS_API_KEY", "test-anahtari")
    fake = SimpleNamespace(
        responses={
            "TP.BIRIMFIYAT.MUGLA": response("TP.BIRIMFIYAT.MUGLA", MUGLA_UNIT_PRICE),
            "TP.KFE.TR32": response("TP.KFE.TR32", TR32_INDEX),
            "TP.AKONUTSAT1.KTR323": response("TP.AKONUTSAT1.KTR323", MUGLA_SALES),
        },
        requested=[],
    )

    async def fake_fetch(path: str):
        code = path.removeprefix("series=").split("&", 1)[0]
        fake.requested.append(code)
        value = fake.responses.get(code, {"totalCount": 0, "items": []})
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(evds, "_fetch", fake_fetch)
    return fake


def stats_for(province: str) -> evds.ProvinceStats:
    return asyncio.run(evds.province_stats(province, today=date(2026, 9, 11)))


def test_series_tables_cover_every_province_once():
    provinces = sorted(fold(p) for p in SALES_SERIES)  # 81 ilin resmî listesi
    assert sorted(fold(p) for members in PRICE_INDEX_REGIONS.values() for p in members) == provinces
    assert sorted(fold(p) for p in SALES_SERIES) == provinces
    assert {fold(p) for p in UNIT_PRICE_SERIES} <= set(provinces)
    assert len(UNIT_PRICE_SERIES) == 76  # 5 il için TCMB birim fiyat yayımlamıyor


@pytest.mark.parametrize(
    ("label", "expected"),
    [("2026-7", "Temmuz 2026"), ("2025-12", "Aralık 2025"), ("2026-1", "Ocak 2026"), ("2026-Q2", "2026 2. çeyrek")],
)
def test_format_period(label, expected):
    assert evds.format_period(label) == expected


def test_province_stats_summarizes_three_series(fake_evds):
    stats = stats_for("MUĞLA")

    assert stats.province == "Muğla"
    assert stats.unit_price == evds.UnitPrice(value=82290, period="2026 2. çeyrek", change_pct=4.1)

    index = stats.price_index
    assert (index.region, index.value, index.period) == ("Aydın, Denizli, Muğla", 174, "Temmuz 2026")
    assert index.change_pct == pytest.approx(7.4)  # 174 / 162
    assert len(index.history) == 25
    assert index.history[0].period == "Temmuz 2024"

    assert stats.sales == evds.Sales(last_12_months=13200, period="Temmuz 2026", change_pct=10.0)


def test_empty_periods_are_skipped(fake_evds):
    fake_evds.responses["TP.KFE.TR32"] = response("TP.KFE.TR32", TR32_INDEX[:-1] + [("2026-7", None)])
    assert stats_for("Muğla").price_index.period == "Haziran 2026"


def test_one_failing_series_does_not_hide_the_others(fake_evds):
    fake_evds.responses["TP.KFE.TR32"] = UpstreamError("EVDS kapalı")
    stats = stats_for("Muğla")
    assert stats.price_index is None
    assert stats.unit_price is not None and stats.sales is not None


def test_all_series_failing_raises_upstream_error(fake_evds):
    for code in list(fake_evds.responses):
        fake_evds.responses[code] = UpstreamError("TCMB EVDS servisine ulaşılamadı.")
    with pytest.raises(UpstreamError):
        stats_for("Muğla")


def test_province_without_unit_price_skips_that_series(fake_evds):
    fake_evds.responses["TP.KFE.TR9"] = response("TP.KFE.TR9", TR32_INDEX)
    stats = stats_for("Gümüşhane")

    assert stats.unit_price is None
    assert stats.price_index.region.startswith("Trabzon")
    assert not any(code.startswith("TP.BIRIMFIYAT") for code in fake_evds.requested)


def test_unknown_province_raises_not_found(fake_evds):
    with pytest.raises(NotFound):
        stats_for("Atlantis")


def test_responses_are_cached(fake_evds):
    stats_for("Muğla")
    stats_for("Muğla")
    assert fake_evds.requested.count("TP.KFE.TR32") == 1


def test_health_reports_whether_stats_are_enabled(client, monkeypatch):
    assert client.get("/api/health").json()["stats"] is False
    monkeypatch.setenv("EVDS_API_KEY", "test-anahtari")
    assert client.get("/api/health").json()["stats"] is True


def test_stats_endpoint_requires_key(client):
    response = client.get("/api/stats/Muğla")
    assert response.status_code == 503
    assert "EVDS_API_KEY" in response.json()["detail"]


def test_stats_endpoint(client, fake_evds):
    body = client.get("/api/stats/Muğla").json()
    assert body["unit_price"]["value"] == 82290
    assert body["price_index"]["change_pct"] == pytest.approx(7.4)
    assert len(body["price_index"]["history"]) == 25
    assert body["sales"]["last_12_months"] == 13200


def test_stats_endpoint_errors(client, fake_evds):
    assert client.get("/api/stats/Atlantis").status_code == 404
    for code in list(fake_evds.responses):
        fake_evds.responses[code] = UpstreamError("TCMB EVDS servisine ulaşılamadı.")
    response = client.get("/api/stats/Muğla")
    assert response.status_code == 502
    assert "ulaşılamadı" in response.json()["detail"]
