"""
OpenStreetMap Nominatim istemcisi.

İki iş için kullanılır: yer arama ve TKGM'de parsel kaydı bulunmayan noktaların
il/ilçe/mahalle bilgisini çözmek. Kullanım politikası gereği saniyede en fazla
bir istek atılır ve tanımlayıcı bir User-Agent gönderilir:
https://operations.osmfoundation.org/policies/nominatim/
"""

import asyncio
import time
from typing import Any

import httpx

from .data import fold
from .errors import UpstreamError

BASE_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "Degerix/3.0 (arsa degerleme portfolyo projesi)"
MIN_INTERVAL_S = 1.0

_client: httpx.AsyncClient | None = None
_lock = asyncio.Lock()
_last_request = 0.0


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "tr"},
            timeout=10,
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _get(path: str, params: dict[str, Any]) -> Any:
    global _last_request
    async with _lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            response = await _get_client().get(path, params=params)
        except httpx.HTTPError as exc:
            raise UpstreamError("Adres servisine (OpenStreetMap) ulaşılamadı.") from exc
        finally:
            _last_request = time.monotonic()

    if response.status_code != 200:
        raise UpstreamError(f"Adres servisi hata döndürdü ({response.status_code}).")
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamError("Adres servisinden geçersiz yanıt alındı.") from exc


def _first(address: dict[str, str], *keys: str) -> str | None:
    return next((address[key] for key in keys if address.get(key)), None)


async def reverse(lat: float, lng: float) -> dict[str, str | None] | None:
    """Koordinatın il/ilçe/mahalle bilgisi; Türkiye dışında ya da adres yoksa None."""
    data = await _get("/reverse", {
        "lat": f"{lat:.6f}", "lon": f"{lng:.6f}",
        "format": "jsonv2", "zoom": 16, "addressdetails": 1,
    })
    address = (data.get("address") or {}) if isinstance(data, dict) else {}
    if address.get("country_code") != "tr":
        return None

    province = address.get("province") or address.get("state")
    district = _first(address, "town", "county", "municipality", "city")
    if not province or not district:
        return None
    if fold(district) == fold(province):  # TKGM il merkezlerini "Merkez" ilçesi olarak tutar
        district = "Merkez"

    return {
        "province": province,
        "district": district,
        "neighborhood": _first(address, "suburb", "neighbourhood", "quarter", "village", "city_district"),
    }


async def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    data = await _get("/search", {"q": query, "format": "jsonv2", "countrycodes": "tr", "limit": limit})
    if not isinstance(data, list):
        return []
    return [
        {"name": item["display_name"], "lat": float(item["lat"]), "lng": float(item["lon"])}
        for item in data
        if isinstance(item, dict) and {"display_name", "lat", "lon"} <= item.keys()
    ]
