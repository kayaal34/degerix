"""
Parselin yerleşim bağlamı: kentleşme derecesi sınıfı, nüfus yoğunluğu ve en yakın
il merkezi, ilçe merkezi ve yerleşim.

Veriler tools/build_urbanity.py ve tools/build_settlements.py ile hazırlanan statik
dosyalardan okunur. Çalışma anında ağ erişimi, rasterio ya da numpy gerekmez.

Kaynaklar: WorldPop 2020 nüfus ızgarası ve GeoNames yerleşim listesi (ikisi de CC BY 4.0).
Sınıflar Birleşmiş Milletler kentleşme derecesi (Degree of Urbanisation) eşiklerine göre
üretilmiştir; kodlar GHS-SMOD ile aynıdır.
"""

import csv
import gzip
import json
import math
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .geo import haversine_km

DATA_DIR = Path(__file__).resolve().parent / "static_data"
GRID_FILE = DATA_DIR / "urbanity_tr.bin.gz"
SETTLEMENTS_FILE = DATA_DIR / "settlements_tr.csv.gz"

URBAN_CENTRE = 30
DENSE_CLUSTER = 23
TOWN = 22
SUBURBAN = 21
VILLAGE = 13
LOW_RURAL = 12
VERY_LOW_RURAL = 11
EMPTY = 10

CLASS_LABELS: dict[int, str] = {
    URBAN_CENTRE: "şehir merkezi",
    DENSE_CLUSTER: "yoğun kentsel küme",
    TOWN: "kasaba",
    SUBURBAN: "şehir çeperi",
    VILLAGE: "köy",
    LOW_RURAL: "seyrek kırsal",
    VERY_LOW_RURAL: "çok seyrek kırsal",
    EMPTY: "nüfussuz alan",
}

PROVINCE_CENTRE_CODES = ("PPLC", "PPLA")
DISTRICT_CENTRE_CODES = ("PPLA2",)

_BUCKET_DEGREES = 0.25
_NEARBY_RADIUS_CELLS = 2  # ~2 km: parsel yerleşimin hemen kenarındaysa da bağlamı görelim


@dataclass(frozen=True)
class Place:
    name: str
    code: str
    population: int
    distance_km: float


@dataclass(frozen=True)
class Urbanity:
    """Parselin bulunduğu 1 km² hücrenin yerleşim bağlamı."""

    # Merkezler coğrafi olarak en yakın olanlardır, idari bağlılığı göstermez:
    # Samsun Alaçam'daki bir köye en yakın il merkezi Sinop olabilir. Parselin gerçek
    # il ve ilçesi TKGM kaydından gelir; buradaki alanlar uzaklık hesabı içindir.
    class_code: int
    label: str
    density: float                     # kişi/km²
    nearby_class: int                  # 2 km çevredeki en kentsel sınıf
    province_centre: Place | None      # en yakın il merkezi (coğrafi)
    district_centre: Place | None      # en yakın ilçe merkezi (coğrafi)
    settlement: Place | None           # en yakın herhangi bir yerleşim (köy dahil)

    @property
    def is_rural(self) -> bool:
        return self.class_code <= VILLAGE


@lru_cache(maxsize=1)
def _grid() -> tuple[dict, bytes, bytes]:
    payload = gzip.decompress(GRID_FILE.read_bytes())
    magic, header_length = struct.unpack_from("<4sI", payload, 0)
    if magic != b"DGX1":
        raise ValueError("Kentsellik dosyası tanınmadı; tools/build_urbanity.py ile yeniden üretin.")
    start = 8 + header_length
    header = json.loads(payload[8:start])
    cells = header["width"] * header["height"]
    classes = payload[start:start + cells]
    density = payload[start + cells:start + 2 * cells]
    if len(density) != cells:
        raise ValueError("Kentsellik dosyası eksik.")
    return header, classes, density


@lru_cache(maxsize=1)
def _settlements() -> dict[tuple[int, int], list[tuple[str, float, float, str, int]]]:
    buckets: dict[tuple[int, int], list[tuple[str, float, float, str, int]]] = {}
    with gzip.open(SETTLEMENTS_FILE, "rt", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            lat, lng = float(row["lat"]), float(row["lng"])
            key = (math.floor(lat / _BUCKET_DEGREES), math.floor(lng / _BUCKET_DEGREES))
            buckets.setdefault(key, []).append((row["name"], lat, lng, row["code"], int(row["population"])))
    return buckets


def _cell(lat: float, lng: float) -> tuple[int, int] | None:
    header, _, _ = _grid()
    column = int((lng - header["west"]) / header["res_lng"])
    row = int((header["north"] - lat) / header["res_lat"])
    if not (0 <= row < header["height"] and 0 <= column < header["width"]):
        return None
    return row, column


def _class_at(row: int, column: int) -> int:
    header, classes, _ = _grid()
    return classes[row * header["width"] + column]


def _density_at(row: int, column: int) -> float:
    """Izgarada saklanan 0-255 değeri kişi/km²'ye çevrilir."""
    header, _, density = _grid()
    return 2 ** (density[row * header["width"] + column] / 16) - 1


def _nearest(lat: float, lng: float, codes: tuple[str, ...] | None, max_km: float) -> Place | None:
    """Verilen özellik kodlarına uyan en yakın yerleşim; yoksa None."""
    buckets = _settlements()
    centre_key = (math.floor(lat / _BUCKET_DEGREES), math.floor(lng / _BUCKET_DEGREES))
    best: Place | None = None

    for ring in range(0, int(max_km / (_BUCKET_DEGREES * 111)) + 2):
        # Halkanın en yakın noktası bulunandan uzaksa aramayı bitir
        ring_distance_km = (ring - 1) * _BUCKET_DEGREES * 111
        if best is not None and ring_distance_km > best.distance_km:
            break
        for row in range(centre_key[0] - ring, centre_key[0] + ring + 1):
            for column in range(centre_key[1] - ring, centre_key[1] + ring + 1):
                if ring and max(abs(row - centre_key[0]), abs(column - centre_key[1])) != ring:
                    continue  # yalnızca halkanın kenarı
                for name, place_lat, place_lng, code, population in buckets.get((row, column), ()):
                    if codes is not None and code not in codes:
                        continue
                    distance = haversine_km(lat, lng, place_lat, place_lng)
                    if distance <= max_km and (best is None or distance < best.distance_km):
                        best = Place(name=name, code=code, population=population, distance_km=round(distance, 2))
    return best


@lru_cache(maxsize=2048)
def describe(lat: float, lng: float) -> Urbanity | None:
    """Koordinatın yerleşim bağlamı; Türkiye ızgarasının dışındaysa None."""
    cell = _cell(lat, lng)
    if cell is None:
        return None
    row, column = cell
    header, _, _ = _grid()

    nearby = EMPTY
    for delta_row in range(-_NEARBY_RADIUS_CELLS, _NEARBY_RADIUS_CELLS + 1):
        for delta_column in range(-_NEARBY_RADIUS_CELLS, _NEARBY_RADIUS_CELLS + 1):
            neighbour_row, neighbour_column = row + delta_row, column + delta_column
            if 0 <= neighbour_row < header["height"] and 0 <= neighbour_column < header["width"]:
                nearby = max(nearby, _class_at(neighbour_row, neighbour_column))

    class_code = _class_at(row, column)
    return Urbanity(
        class_code=class_code,
        label=CLASS_LABELS.get(class_code, "bilinmiyor"),
        density=round(_density_at(row, column), 1),
        nearby_class=nearby,
        province_centre=_nearest(lat, lng, PROVINCE_CENTRE_CODES, max_km=400),
        district_centre=_nearest(lat, lng, DISTRICT_CENTRE_CODES, max_km=120),
        settlement=_nearest(lat, lng, None, max_km=25),
    )
