"""Testler ağa çıkmaz: TKGM ve Nominatim çağrıları sabit verilerle değiştirilir."""

import copy

import pytest
from fastapi.testclient import TestClient

from app import main, nominatim, tkgm
from app.errors import NotFound


def square(lat: float, lng: float, half: float) -> dict:
    ring = [[lng - half, lat - half], [lng + half, lat - half], [lng + half, lat + half], [lng - half, lat + half], [lng - half, lat - half]]
    return {"type": "Polygon", "coordinates": [ring]}


def collection(*items: tuple[str, int, dict | None]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"text": name, "id": place_id}, "geometry": geometry}
            for name, place_id, geometry in items
        ],
    }


BODRUM_PARCEL = {
    "type": "Feature",
    "properties": {
        "ilAd": "Muğla", "ilId": 70,
        "ilceAd": "Bodrum", "ilceId": 724,
        "mahalleAd": "Yenikoy", "mahalleId": 122420,  # TKGM'nin bozuk yazımı
        "adaNo": "1108", "parselNo": "6",
        "alan": "467,87",
        "nitelik": "Avlulu Kargir Ev Ve Dam",
    },
    "geometry": square(37.0385, 27.4190, 0.0001),
}

TKGM_RESPONSES = {
    "/idariYapi/ilListe": collection(("Muğla", 70, None)),
    "/idariYapi/ilceListe/70": collection(("Bodrum", 724, square(37.05, 27.40, 0.12))),
    "/idariYapi/mahalleListe/724": collection(("Yeniköy", 122420, None)),
    "/parsel/37.038500/27.419000/": BODRUM_PARCEL,
    "/parsel/122420/1108/6": BODRUM_PARCEL,
}


@pytest.fixture
def fake_tkgm(monkeypatch):
    """Yol → yanıt sözlüğü döndürür; testler içeriğini değiştirebilir."""
    responses = copy.deepcopy(TKGM_RESPONSES)

    async def fake_fetch(path: str):
        if path not in responses:
            raise NotFound("TKGM'de bu kayıt bulunamadı.")
        value = responses[path]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    tkgm.clear_cache()
    monkeypatch.setattr(tkgm, "_fetch", fake_fetch)
    yield responses
    tkgm.clear_cache()


@pytest.fixture
def client(fake_tkgm, monkeypatch):
    async def fake_reverse(lat: float, lng: float):
        if lat < 37.0:  # testlerde "deniz"
            return None
        return {"province": "Muğla", "district": "Bodrum", "neighborhood": "Gündoğan"}

    async def fake_search(query: str, limit: int = 5):
        return [{"name": f"{query}, Bodrum, Muğla, Türkiye", "lat": 37.1, "lng": 27.3}]

    # Geliştiricinin .env anahtarı testlere sızmasın: değerleme konut fiyatını
    # canlı EVDS yerine app/static_data içindeki kopyadan alsın.
    monkeypatch.delenv("EVDS_API_KEY", raising=False)

    async def no_surroundings(lat: float, lng: float):
        return None  # çevre ölçümleri ayrı test ediliyor; burada ağa çıkılmaz

    monkeypatch.setattr(nominatim, "reverse", fake_reverse)
    monkeypatch.setattr(nominatim, "search", fake_search)
    monkeypatch.setattr("app.nearby.fetch", no_surroundings)

    with TestClient(main.app) as test_client:
        yield test_client
