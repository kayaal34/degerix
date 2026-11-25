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

# Sınıflar en kırsaldan en kentsele doğru sıralı. Kodlar (10, 11, 12, 13, 21, 22, 23, 30)
# eşit aralıklı olmadığı için mesafe sönümlemesi kod üzerinde değil bu basamak
# indeksi üzerinde yapılır.
CLASS_ORDER = (EMPTY, VERY_LOW_RURAL, LOW_RURAL, VILLAGE, SUBURBAN, TOWN, DENSE_CLUSTER, URBAN_CENTRE)
_RUNG: dict[int, int] = {code: index for index, code in enumerate(CLASS_ORDER)}

_BUCKET_DEGREES = 0.25
_NEARBY_RADIUS_CELLS = 2  # ~2 km: parsel yerleşimin hemen kenarındaysa da bağlamı görelim

# Erişilebilirlik: parsel çevresindeki en kentsel hücreyi, uzaklığına göre basamak
# basamak indirerek devralır. 1 km'lik hücrenin kendi nüfus yoğunluğu erişilebilirliği
# temsil etmiyor: Gaziantep merkezine 8,6 km'deki boş bir parsel "seyrek kırsal"
# görünüyor, oysa orada fiyatı tarımsal verim değil şehre yakınlık belirliyor.
# Basamak uzunluğu coğrafi bir varsayımdır: Türkiye'de şehir merkezinden gerçek
# kırsala geçiş 40 km mertebesinde ve arada 7 basamak var, yani basamak ≈ 6 km.
# Bu, en kentsel kaynağın (şehir merkezi) menzilidir; daha kırsal kaynaklar
# basamaklarıyla oranlı olarak daha kısa menzile sahiptir, çünkü bir şehrin etkisi
# uzağa gider, bir köyün gitmez: 6 km ötedeki köy, 4 kişi/km² yoğunluklu bir hücreyi
# köy sınıfına çıkarmamalı.
ACCESS_STEP_KM = 6.0
ACCESS_MAX_KM = 45.0


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
    metro: Place | None = None         # çekim alanındaki en güçlü büyükşehir (nüfus/mesafe²)
    # Çevredeki en kentsel sınıf, uzaklığa göre basamak basamak indirilmiş. Varsayılanı
    # EMPTY: bilinmiyorsa etkisi olmaz, çünkü sınıf seçimi en kentsel olanı alıyor.
    access_class: int = EMPTY

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


def _strongest(lat: float, lng: float, codes: tuple[str, ...] | None, max_km: float,
               min_population: int = 0) -> Place | None:
    """√nüfus / mesafe² skoruyla en 'çekici' merkezi seçer.

    En yakın merkez her zaman en ilgili merkez değildir: Gebze'deki bir parsele
    Şile (20 km, 20 bin kişi) Gebze'den (25 km, 281 bin kişi) daha yakındır.
    Nüfusun karekökü alınır, yoksa büyük şehir yakındaki kendi ilçe merkezini
    ezer: Mudanya'daki parsel 100 m ötedeki Mudanya yerine 18 km'deki Nilüfer'e
    bağlanırdı. Büyükşehir etkisini ayrıca `metro` alanı taşıyor.
    Skor mesafeyle monoton azalmadığı için max_km içindeki tüm adaylar taranır.
    """
    buckets = _settlements()
    centre_key = (math.floor(lat / _BUCKET_DEGREES), math.floor(lng / _BUCKET_DEGREES))
    best: Place | None = None
    best_score = -1.0
    span = int(max_km / (_BUCKET_DEGREES * 111)) + 2
    for row in range(centre_key[0] - span, centre_key[0] + span + 1):
        for column in range(centre_key[1] - span, centre_key[1] + span + 1):
            for name, place_lat, place_lng, code, population in buckets.get((row, column), ()):
                if (codes is not None and code not in codes) or population < min_population:
                    continue
                distance = haversine_km(lat, lng, place_lat, place_lng)
                if distance > max_km:
                    continue
                score = math.sqrt(population) / (distance + 10) ** 2
                if score > best_score:
                    best_score = score
                    best = Place(name=name, code=code, population=population, distance_km=round(distance, 2))
    return best


def rung(class_code: int) -> int:
    """Sınıf kodunun kırsaldan kentsele sıralı basamak indeksi (kodlar eşit aralıklı değil)."""
    return _RUNG.get(class_code, 0)


def _access_class(row: int, column: int) -> int:
    """Çevredeki en kentsel sınıfı uzaklığa göre indirerek devralır.

    Her hücre için `basamak - mesafe / ACCESS_STEP_KM` puanı hesaplanır, en yüksek
    puan kazanır. Parselin kendi hücresi 0 km'de olduğu için sonuç hiçbir zaman
    hücrenin kendi sınıfının altına düşmez; ızgarada olmayan bir kentsellik de
    uydurulmaz, yalnızca var olan kentsellik mesafeyle sönümlenerek taşınır.
    """
    header, _, _ = _grid()
    latitude = header["north"] - (row + 0.5) * header["res_lat"]
    km_per_row = header["res_lat"] * 111.0
    km_per_column = header["res_lng"] * 111.0 * max(math.cos(math.radians(latitude)), 0.01)
    max_row_steps = int(ACCESS_MAX_KM / km_per_row) + 1
    max_column_steps = int(ACCESS_MAX_KM / km_per_column) + 1
    top_rung = len(CLASS_ORDER) - 1

    best = float(_RUNG.get(_class_at(row, column), 0))
    for ring in range(1, max(max_row_steps, max_column_steps) + 1):
        # Halkanın en yakın noktası bile en kentsel sınıfla bu puanı geçemiyorsa bitir.
        reachable = top_rung - ((ring - 1) * min(km_per_row, km_per_column)) / ACCESS_STEP_KM
        if reachable <= best:
            break
        for delta_row in range(-ring, ring + 1):
            if abs(delta_row) > max_row_steps:
                continue
            for delta_column in range(-ring, ring + 1):
                if max(abs(delta_row), abs(delta_column)) != ring:
                    continue  # yalnızca halkanın kenarı
                if abs(delta_column) > max_column_steps:
                    continue
                neighbour_row, neighbour_column = row + delta_row, column + delta_column
                if not (0 <= neighbour_row < header["height"] and 0 <= neighbour_column < header["width"]):
                    continue
                distance = math.hypot(delta_row * km_per_row, delta_column * km_per_column)
                if distance > ACCESS_MAX_KM:
                    continue
                source_rung = _RUNG.get(_class_at(neighbour_row, neighbour_column), 0)
                if source_rung == 0:
                    continue  # nüfussuz hücre hiçbir yeri yukarı çekmez
                # Menzil kaynağın kentselliğiyle oranlı: şehir merkezi 6 km'de bir
                # basamak kaybeder, köy yaklaşık 2,5 km'de bir.
                step_km = ACCESS_STEP_KM * source_rung / top_rung
                score = source_rung - distance / step_km
                if score > best:
                    best = score
    # Kesme değil yuvarlama: 1,5 km'deki şehir merkezi hücresi 6,75 puan alır ve
    # kesme onu bir basamak aşağıya, yoğun kentsel kümeye düşürürdü. Parselin kendi
    # hücresi 0 km'de olduğu için sonuç yine hücrenin sınıfının altına düşemez.
    return CLASS_ORDER[max(0, min(top_rung, round(best)))]


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
        access_class=_access_class(row, column),
        province_centre=_nearest(lat, lng, PROVINCE_CENTRE_CODES, max_km=400),
        district_centre=_strongest(lat, lng, DISTRICT_CENTRE_CODES, max_km=120, min_population=5_000),
        settlement=_nearest(lat, lng, None, max_km=25),
        metro=_strongest(lat, lng, ("PPLC", "PPLA", "PPLA2"), max_km=150, min_population=250_000),
    )
