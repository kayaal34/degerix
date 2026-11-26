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
from .surroundings import (
    BUILDINGS_RADIUS_M,
    BUILT_UP_RADIUS_M,
    COAST_RADIUS_M,
    MAIN_ROAD_RADIUS_M,
    SERVICES_RADIUS_M,
    OsmContext,
    Surroundings,
)

# Sorgu ağırlaştıkça ana Overpass örneği gün içinde 40 saniyeye kadar çıkıyor, zaman
# zaman 502 veriyor; aynı sorgu Fransa aynasında 8 saniye sürüyor. Sırayla denenir,
# ikisi de yetişmezse çevre ölçümü atlanır (fetch_within bütçesi).
OVERPASS_URLS = (
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
USER_AGENT = "Degerix/4.0 (arsa degerleme portfolyo projesi)"
SLOPE_OFFSET_M = 60  # 90 m çözünürlüklü yükselti modelinde anlamlı en küçük adım
CACHE_TTL_S = 24 * 3600

_cache: dict[str, tuple[float, Surroundings]] = {}

_QUERY = """[out:json][timeout:25];
(
  way["natural"="coastline"](around:{coast},{lat},{lng});
  way["highway"~"^(motorway|trunk|primary|secondary)$"](around:{road},{lat},{lng});
  way["landuse"~"^(residential|commercial|industrial|retail)$"](around:{built_up},{lat},{lng});
);
out tags geom;
(
  nwr["amenity"~"^(school|kindergarten|university|hospital|clinic|doctors|pharmacy)$"](around:{services},{lat},{lng});
  nwr["shop"~"^(supermarket|convenience)$"](around:{services},{lat},{lng});
);
out tags center;
way["building"](around:{buildings},{lat},{lng});
out count;"""


CACHE_MAX = 2000


def clear_cache() -> None:
    _cache.clear()


def _prune_cache(now: float) -> None:
    """Süresi geçenleri at; hâlâ büyükse en erken sona erecekleri at.

    Önbellek yalnızca eklenip hiç temizlenmiyordu: uzun süre ayakta kalan bir
    sunucuda her yeni koordinat kalıcı bir satır bırakıyor ve bellek sessizce
    büyüyor. Ücretsiz sunucu planında bu, süreç ölene kadar sürer.
    """
    for anahtar in [k for k, (biter, _) in _cache.items() if biter <= now]:
        _cache.pop(anahtar, None)
    if len(_cache) > CACHE_MAX:
        for anahtar in sorted(_cache, key=lambda k: _cache[k][0])[:len(_cache) - CACHE_MAX]:
            _cache.pop(anahtar, None)


# Arka plan ölçümlerinin toplam eşzamanlılık sınırı. Sınırsızken bot, tarama ya da
# çoklu sekme onlarca farklı koordinat getirince Overpass'a aynı anda onlarca sorgu
# gidiyordu; ağır sorgusu yüzünden ana örnek zaten 40 sn'ye çıkıyor ve ücretsiz
# kullanım politikası birkaç eşzamanlı yuvaya izin veriyor. 4: tek örnek için
# nazik, ama iki-üç sekmenin aynı anda değerlemesini kuyruğa sokmayacak kadar geniş.
# Open-Meteo hafif ve hızlı olduğundan daha geniş bir sınır yeter.
OSM_MAX_CONCURRENT = 4
SLOPE_MAX_CONCURRENT = 8
# Uçuştaki farklı koordinat sayısı sınırı; aşılırsa yeni nokta için ölçüm başlatılmaz
# (fetch_within None döner, tahmin çevresiz hesaplanır) ve _inflight büyümez.
INFLIGHT_MAX = 200

_slots: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Semaphore]] = {}


def _slot(name: str, size: int) -> asyncio.Semaphore:
    """Çalışan olay döngüsüne bağlı semafor (her asyncio.run yeni döngü açar)."""
    loop = asyncio.get_running_loop()
    hit = _slots.get(name)
    if hit is None or hit[0] is not loop:
        hit = _slots[name] = (loop, asyncio.Semaphore(size))
    return hit[1]


class _Progress:
    """Uçuştaki bir ölçümün o ana kadar gelen parçaları (fetch_within için)."""

    __slots__ = ("osm", "slope")

    def __init__(self) -> None:
        self.osm: OsmContext | None = None
        self.slope: float | None = None


_progress: dict[str, _Progress] = {}


async def fetch(lat: float, lng: float) -> Surroundings:
    key = f"{lat:.5f},{lng:.5f}"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    _prune_cache(now)

    progress = _progress[key] = _Progress()

    async def osm_part(client: httpx.AsyncClient) -> None:
        async with _slot("osm", OSM_MAX_CONCURRENT):
            progress.osm = await _osm_context(client, lat, lng)

    async def slope_part(client: httpx.AsyncClient) -> None:
        async with _slot("slope", SLOPE_MAX_CONCURRENT):
            progress.slope = await _slope_pct(client, lat, lng)

    try:
        # İki servis birbirini beklemez: her parça biter bitmez progress'e yazılır.
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15) as client:
            await asyncio.gather(osm_part(client), slope_part(client))
    finally:
        if _progress.get(key) is progress:
            del _progress[key]
    result = Surroundings(osm=progress.osm, slope_pct=progress.slope)
    if progress.osm is not None and progress.slope is not None:
        # eksik sonuç saklanmaz, sonraki istekte yeniden denenir
        _cache[key] = (now + CACHE_TTL_S, result)
    return result


_inflight: dict[str, asyncio.Task[Surroundings]] = {}


async def fetch_within(lat: float, lng: float, budget_s: float) -> Surroundings | None:
    """Ölçümü en fazla budget_s saniye bekler; yetişmezse o ana kadar gelen parçayı verir.

    Ölçüm iptal edilmez, arka planda sürer ve bitince (eksiksizse) önbelleğe yazılır;
    böylece değer tahmini yavaş bir dış servisi beklemez. Bütçe dolduğunda yalnız
    biri gelmişse (örn. eğim var, OSM yok) o parça döner; hiçbiri gelmediyse None.
    Aynı nokta için eşzamanlı istekler tek ölçümü paylaşır.
    """
    key = f"{lat:.5f},{lng:.5f}"
    task = _inflight.get(key)
    if task is None:
        if len(_inflight) >= INFLIGHT_MAX:
            return None
        task = asyncio.create_task(fetch(lat, lng))
        _inflight[key] = task
        task.add_done_callback(lambda _: _inflight.pop(key, None))
    try:
        return await asyncio.wait_for(asyncio.shield(task), budget_s)
    except TimeoutError:
        part = _progress.get(key)
        if part is not None and (part.osm is not None or part.slope is not None):
            return Surroundings(osm=part.osm, slope_pct=part.slope)
        return None


def _inside(lat: float, lng: float, ring: list[tuple[float, float]]) -> bool:
    """Işın atma: nokta poligonun içinde mi."""
    crossings = 0
    for (y1, x1), (y2, x2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and x1 + (lat - y1) * (x2 - x1) / (y2 - y1) > lng:
            crossings += 1
    return crossings % 2 == 1


class OverpassRemark(ValueError):
    """Overpass hatayı HTTP 200 ile döndürdü."""


def parse_overpass(data: dict[str, Any], lat: float, lng: float) -> OsmContext:
    # Overpass sunucu hatasını 200 ile, gövdede "remark" alanıyla bildiriyor:
    # {"version":..., "remark": "runtime error: Query timed out", "elements": []}
    # Bunu ayırmazsak boş liste "0 bina, kıyı yok, yol yok" diye okunuyor —
    # ölçülmemiş bir parsel ölçülmüş gibi görünüyor, imar beklentisi primi
    # sessizce düşüyor ve bu yanlış sonuç 24 saat önbellekte kalıyor.
    # Eksik ölçüm, yanlış ölçümden iyidir: hata verip None'a düşelim.
    remark = str(data.get("remark") or "")
    if remark:
        raise OverpassRemark(remark[:200])
    if "elements" not in data:
        raise OverpassRemark("yanıtta elements alanı yok")

    coast = road = built_up = math.inf
    services = buildings = 0
    sayim_geldi = False
    for element in data.get("elements", []):
        tags = element.get("tags") or {}
        if element.get("type") == "count":
            buildings = int(tags.get("ways", 0) or 0)
            sayim_geldi = True
        elif "geometry" in element and "landuse" in tags:
            ring = [(point["lat"], point["lon"]) for point in element["geometry"] if point]
            if len(ring) >= 3:
                built_up = min(built_up, 0.0 if _inside(lat, lng, ring)
                               else distance_to_line_m(lat, lng, ring))
        elif "geometry" in element and (tags.get("natural") == "coastline" or "highway" in tags):
            line = [(point["lat"], point["lon"]) for point in element["geometry"] if point]
            distance = distance_to_line_m(lat, lng, line)
            if tags.get("natural") == "coastline":
                coast = min(coast, distance)
            else:
                road = min(road, distance)
        elif "amenity" in tags or "shop" in tags:
            services += 1

    # Sorgu "out count;" ile bitiyor, yani eksiksiz her yanıtta — kırın
    # ortasında bile — sıfır değerli bir sayım satırı bulunur. Satır yoksa
    # yanıt yarım kesilmiştir; "0 bina" diye okumak, ölçülmemiş bir parseli
    # ölçülmüş saymak olur ve imar beklentisi primini sessizce düşürür.
    if not sayim_geldi:
        raise OverpassRemark("yanıtta bina sayım satırı yok, ölçüm yarım")

    return OsmContext(
        coast_m=None if math.isinf(coast) else round(coast),
        main_road_m=None if math.isinf(road) else round(road),
        services=services,
        buildings=buildings,
        built_up_m=None if math.isinf(built_up) else round(built_up),
    )


async def _osm_context(client: httpx.AsyncClient, lat: float, lng: float) -> OsmContext | None:
    query = _QUERY.format(
        coast=COAST_RADIUS_M, road=MAIN_ROAD_RADIUS_M, services=SERVICES_RADIUS_M,
        built_up=BUILT_UP_RADIUS_M, buildings=BUILDINGS_RADIUS_M,
        lat=f"{lat:.6f}", lng=f"{lng:.6f}",
    )
    for url in OVERPASS_URLS:
        try:
            response = await client.post(url, data={"data": query})
            response.raise_for_status()
            return parse_overpass(response.json(), lat, lng)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            # OverpassRemark da ValueError; sıradaki aynaya geçilir
            continue
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
