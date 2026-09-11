"""
Parsel çevresi ölçümleri.

- OpenStreetMap Overpass API: kıyı çizgisi, ana yollar, okul / sağlık / market noktaları
- Open-Meteo Elevation API: Copernicus 90 m yükselti modeli → eğim

İkisi de ücretsiz ve anahtarsızdır ama adil kullanım sınırı vardır; sonuçlar koordinata
göre bir gün bellekte tutulur. Bir servis yanıt vermezse o ölçüm atlanır.
"""

import asyncio
import math
import time
from typing import Any

import httpx

from .geo import KM_PER_DEG_LAT, KM_PER_DEG_LNG_AT_EQUATOR, distance_to_line_m
from .surroundings import COAST_RADIUS_M, MAIN_ROAD_RADIUS_M, SERVICES_RADIUS_M, OsmContext, Surroundings

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
USER_AGENT = "Degerix/3.3 (arsa degerleme portfolyo projesi)"
SLOPE_OFFSET_M = 60  # 90 m çözünürlüklü yükselti modelinde anlamlı en küçük adım
CACHE_TTL_S = 24 * 3600

_cache: dict[str, tuple[float, Surroundings]] = {}

_QUERY = """[out:json][timeout:15];
(
  way["natural"="coastline"](around:{coast},{lat},{lng});
  way["highway"~"^(motorway|trunk|primary|secondary)$"](around:{road},{lat},{lng});
);
out tags geom;
(
  nwr["amenity"~"^(school|kindergarten|university|hospital|clinic|doctors|pharmacy)$"](around:{services},{lat},{lng});
  nwr["shop"~"^(supermarket|convenience)$"](around:{services},{lat},{lng});
);
out tags center;"""


def clear_cache() -> None:
    _cache.clear()


async def fetch(lat: float, lng: float) -> Surroundings:
    key = f"{lat:.5f},{lng:.5f}"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15) as client:
        osm, slope = await asyncio.gather(_osm_context(client, lat, lng), _slope_pct(client, lat, lng))
    result = Surroundings(osm=osm, slope_pct=slope)
    if osm is not None and slope is not None:  # eksik sonuç saklanmaz, sonraki istekte yeniden denenir
        _cache[key] = (now + CACHE_TTL_S, result)
    return result


def parse_overpass(data: dict[str, Any], lat: float, lng: float) -> OsmContext:
    coast = road = math.inf
    services = 0
    for element in data.get("elements", []):
        tags = element.get("tags") or {}
        if "geometry" in element and (tags.get("natural") == "coastline" or "highway" in tags):
            line = [(point["lat"], point["lon"]) for point in element["geometry"] if point]
            distance = distance_to_line_m(lat, lng, line)
            if tags.get("natural") == "coastline":
                coast = min(coast, distance)
            else:
                road = min(road, distance)
        elif "amenity" in tags or "shop" in tags:
            services += 1
    return OsmContext(
        coast_m=None if math.isinf(coast) else round(coast),
        main_road_m=None if math.isinf(road) else round(road),
        services=services,
    )


async def _osm_context(client: httpx.AsyncClient, lat: float, lng: float) -> OsmContext | None:
    query = _QUERY.format(
        coast=COAST_RADIUS_M, road=MAIN_ROAD_RADIUS_M, services=SERVICES_RADIUS_M,
        lat=f"{lat:.6f}", lng=f"{lng:.6f}",
    )
    try:
        response = await client.post(OVERPASS_URL, data={"data": query})
        response.raise_for_status()
        return parse_overpass(response.json(), lat, lng)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


async def _slope_pct(client: httpx.AsyncClient, lat: float, lng: float) -> float | None:
    d_lat = SLOPE_OFFSET_M / (KM_PER_DEG_LAT * 1000)
    d_lng = SLOPE_OFFSET_M / (KM_PER_DEG_LNG_AT_EQUATOR * 1000 * math.cos(math.radians(lat)))
    points = [(lat + d_lat, lng), (lat - d_lat, lng), (lat, lng + d_lng), (lat, lng - d_lng)]  # K, G, D, B
    try:
        response = await client.get(ELEVATION_URL, params={
            "latitude": ",".join(f"{point[0]:.6f}" for point in points),
            "longitude": ",".join(f"{point[1]:.6f}" for point in points),
        })
        response.raise_for_status()
        north, south, east, west = (float(value) for value in response.json()["elevation"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None
    gradient = math.hypot(north - south, east - west) / (2 * SLOPE_OFFSET_M)
    return round(gradient * 100, 1)
