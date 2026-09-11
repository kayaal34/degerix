"""
TKGM Parsel Sorgu (MEGSİS) istemcisi.

parselsorgu.tkgm.gov.tr'nin kullandığı herkese açık uç noktalar:

    /idariYapi/ilListe                     81 il
    /idariYapi/ilceListe/{il_id}           ilçeler (sınır poligonlarıyla)
    /idariYapi/mahalleListe/{ilce_id}      mahalleler
    /parsel/{enlem}/{boylam}/              koordinattaki parsel
    /parsel/{mahalle_id}/{ada}/{parsel}    ada/parsel numarasıyla parsel

Resmî olarak belgelenmiş bir API değildir: biçim değişebilir ve yoğun kullanımda
istek sınırına takılabilir. Bu yüzden idari listeler bir gün, parseller bir saat
bellekte tutulur.
"""

import time
from typing import Any

import httpx

from .errors import NotFound, UpstreamError

BASE_URL = "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3/api"
HEADERS = {
    "User-Agent": "Degerix/3.0 (arsa degerleme portfolyo projesi)",
    "Referer": "https://parselsorgu.tkgm.gov.tr/",
}
ADMIN_TTL_S = 24 * 3600
PARCEL_TTL_S = 3600
MAX_CACHE_ENTRIES = 1000

_client: httpx.AsyncClient | None = None
_cache: dict[str, tuple[float, Any]] = {}


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=15)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def clear_cache() -> None:
    _cache.clear()


async def _fetch(path: str) -> Any:
    try:
        response = await _get_client().get(path)
    except httpx.HTTPError as exc:
        raise UpstreamError("TKGM parsel servisine ulaşılamadı. Biraz sonra tekrar deneyin.") from exc
    if response.status_code == 404:
        raise NotFound("TKGM'de bu kayıt bulunamadı.")
    if response.status_code != 200:
        raise UpstreamError(f"TKGM parsel servisi hata döndürdü ({response.status_code}).")
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamError("TKGM parsel servisinden geçersiz yanıt alındı.") from exc


async def _cached(path: str, ttl_s: float) -> Any:
    now = time.monotonic()
    hit = _cache.get(path)
    if hit is not None and hit[0] > now:
        return hit[1]
    data = await _fetch(path)
    if len(_cache) >= MAX_CACHE_ENTRIES:
        _cache.clear()
    _cache[path] = (now + ttl_s, data)
    return data


def _features(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("features"), list):
        return data["features"]
    raise UpstreamError("TKGM servisinden beklenmeyen biçimde yanıt alındı.")


def _places(data: Any) -> list[dict[str, Any]]:
    places = []
    for feature in _features(data):
        props = feature.get("properties") or {}
        if "id" in props and props.get("text"):
            places.append({"id": props["id"], "name": props["text"]})
    return places


def _name_by_id(places: list[dict[str, Any]], place_id: Any) -> str | None:
    return next((place["name"] for place in places if place["id"] == place_id), None)


async def list_provinces() -> list[dict[str, Any]]:
    return _places(await _cached("/idariYapi/ilListe", ADMIN_TTL_S))


async def list_districts(province_id: int) -> list[dict[str, Any]]:
    return _places(await _cached(f"/idariYapi/ilceListe/{province_id}", ADMIN_TTL_S))


async def list_neighborhoods(district_id: int) -> list[dict[str, Any]]:
    return _places(await _cached(f"/idariYapi/mahalleListe/{district_id}", ADMIN_TTL_S))


def _parcel_feature(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("properties"), dict) and isinstance(data.get("geometry"), dict):
        return data
    raise NotFound("TKGM'de bu kayıt bulunamadı.")


async def parcel_at(lat: float, lng: float) -> dict[str, Any]:
    try:
        data = await _cached(f"/parsel/{lat:.6f}/{lng:.6f}/", PARCEL_TTL_S)
    except NotFound as exc:
        raise NotFound("Bu noktada kayıtlı parsel yok.") from exc
    return _parcel_feature(data)


async def parcel_by_number(neighborhood_id: int, ada: str, parsel: str) -> dict[str, Any]:
    try:
        data = await _cached(f"/parsel/{neighborhood_id}/{ada}/{parsel}", PARCEL_TTL_S)
    except NotFound as exc:
        raise NotFound(f"{ada} ada {parsel} parsel bu mahallede bulunamadı.") from exc
    return _parcel_feature(data)


async def official_names(props: dict[str, Any]) -> tuple[str, str, str | None]:
    """Parsel yanıtındaki il/ilçe/mahalle adlarını idari listelerdeki yazımla değiştirir.

    Parsel uç noktası "Gölbaşi" gibi bozuk yazımlar döndürebiliyor. Listelere
    ulaşılamazsa yanıttaki adlar olduğu gibi kullanılır.
    """
    province = props.get("ilAd") or ""
    district = props.get("ilceAd") or ""
    neighborhood = props.get("mahalleAd") or None
    province_id, district_id = props.get("ilId"), props.get("ilceId")

    try:
        province = _name_by_id(await list_provinces(), province_id) or province
        if province_id is not None:
            district = _name_by_id(await list_districts(province_id), district_id) or district
        if district_id is not None:
            neighborhood = _name_by_id(await list_neighborhoods(district_id), props.get("mahalleId")) or neighborhood
    except (NotFound, UpstreamError):
        pass

    return province, district, neighborhood


def parse_area(value: Any) -> float | None:
    """TKGM alanı "45,911.00" ya da "45.911,00" biçiminde döndürebiliyor; ikisini de çözer."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None

    text = str(value).strip().replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):  # 45.911,00
            text = text.replace(".", "").replace(",", ".")
        else:  # 45,911.00
            text = text.replace(",", "")
    else:
        separator = "," if "," in text else "." if "." in text else None
        if separator:
            tail = text.rsplit(separator, 1)[1]
            is_thousands = text.count(separator) > 1 or len(tail) == 3
            text = text.replace(separator, "" if is_thousands else ".")

    try:
        area = float(text)
    except ValueError:
        return None
    return area if area > 0 else None
