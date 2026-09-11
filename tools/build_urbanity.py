"""
Kentsellik ızgarası üretir: WorldPop 1 km nüfus haritasından Birleşmiş Milletler'in
kentleşme derecesi (Degree of Urbanisation) sınıfları hesaplanır.

    python tools/build_urbanity.py

Girdi : data/source/tur_pop_1km.tif  (yoksa WorldPop'tan indirilir, ~5,6 MB)
Çıktı : app/static_data/urbanity_tr.bin.gz  (sınıf + yoğunluk düzlemi)

Yalnızca veri hazırlarken çalıştırılır; uygulama çalışırken rasterio/numpy/scipy gerekmez.

Kaynak: WorldPop (www.worldpop.org), University of Southampton — Türkiye 2020,
1 km çözünürlük. Lisans: Creative Commons Attribution 4.0.
Yöntem: Degree of Urbanisation (Eurostat/BM) birinci aşama eşikleri.
"""

import gzip
import json
import struct
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import rasterio
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "source" / "tur_pop_1km.tif"
OUTPUT = ROOT / "app" / "static_data" / "urbanity_tr.bin.gz"
SOURCE_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2020/TUR/"
    "tur_ppp_2020_1km_Aggregated.tif"
)

# Sınıf kodları GHS-SMOD ile aynı tutuldu (karşılaştırılabilirlik için)
URBAN_CENTRE = 30       # yoğun çekirdek, kümede en az 50.000 kişi
DENSE_CLUSTER = 23      # yoğun ama küçük şehir
SEMI_DENSE = 22         # kasaba / yarı yoğun kentsel küme
SUBURBAN = 21           # şehrin çeperi
RURAL_CLUSTER = 13      # köy
LOW_RURAL = 12          # seyrek kırsal
VERY_LOW_RURAL = 11     # çok seyrek kırsal
EMPTY = 10              # nüfussuz / su

DENSE_THRESHOLD = 1500          # kişi/km²
MODERATE_THRESHOLD = 300        # kişi/km²
URBAN_CENTRE_POPULATION = 50_000
CLUSTER_POPULATION = 5_000
VILLAGE_POPULATION = 500


def download_source() -> None:
    if SOURCE.exists():
        return
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    print(f"WorldPop nüfus haritası indiriliyor: {SOURCE_URL}")
    with httpx.Client(timeout=300, follow_redirects=True) as client, SOURCE.open("wb") as handle:
        with client.stream("GET", SOURCE_URL) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                handle.write(chunk)
    print(f"  {SOURCE.stat().st_size / 1e6:.1f} MB indirildi")


def classify(population: np.ndarray) -> np.ndarray:
    """Her 1 km² hücre için kentleşme derecesi sınıfı."""
    classes = np.full(population.shape, VERY_LOW_RURAL, dtype=np.uint8)
    classes[population >= 50] = LOW_RURAL
    classes[population <= 0] = EMPTY

    neighbours8 = np.ones((3, 3), dtype=bool)

    # Orta yoğunluklu kümeler: köy, kasaba ve şehir çeperi
    moderate_labels, moderate_count = ndimage.label(population >= MODERATE_THRESHOLD, structure=neighbours8)
    moderate_totals = np.concatenate(
        [[0.0], ndimage.sum(population, moderate_labels, index=np.arange(1, moderate_count + 1))]
    )

    # Yoğun çekirdekler: 4 komşuluk, kentleşme derecesi yönteminin tanımı
    dense_labels, dense_count = ndimage.label(population >= DENSE_THRESHOLD)
    dense_totals = np.concatenate(
        [[0.0], ndimage.sum(population, dense_labels, index=np.arange(1, dense_count + 1))]
    )

    moderate_cell_total = moderate_totals[moderate_labels]
    classes[(moderate_labels > 0) & (moderate_cell_total >= VILLAGE_POPULATION)] = RURAL_CLUSTER
    classes[(moderate_labels > 0) & (moderate_cell_total >= CLUSTER_POPULATION)] = SEMI_DENSE

    dense_cell_total = dense_totals[dense_labels]
    classes[(dense_labels > 0) & (dense_cell_total >= CLUSTER_POPULATION)] = DENSE_CLUSTER
    classes[(dense_labels > 0) & (dense_cell_total >= URBAN_CENTRE_POPULATION)] = URBAN_CENTRE

    # Şehir çeperi: şehir merkezi içeren kümenin yoğun olmayan hücreleri
    centre_labels = set(np.unique(moderate_labels[classes == URBAN_CENTRE])) - {0}
    if centre_labels:
        in_centre_cluster = np.isin(moderate_labels, list(centre_labels))
        classes[in_centre_cluster & (classes == SEMI_DENSE)] = SUBURBAN

    return classes


def log_density(population: np.ndarray) -> np.ndarray:
    """Yoğunluğu 0-255 aralığına sıkıştırır: değer = 16 × log2(1 + kişi/km²)."""
    scaled = 16 * np.log2(1 + np.clip(population, 0, None))
    return np.clip(np.round(scaled), 0, 255).astype(np.uint8)


def main() -> None:
    download_source()
    with rasterio.open(SOURCE) as source:
        population = source.read(1).astype(np.float32)
        transform = source.transform
        nodata = source.nodata
        width, height = source.width, source.height
    if nodata is not None:
        population[population == nodata] = 0.0
    population[~np.isfinite(population)] = 0.0

    classes = classify(population)
    density = log_density(population)

    header = {
        "format": "degerix-urbanity-1",
        "west": transform.c,
        "north": transform.f,
        "res_lng": transform.a,
        "res_lat": -transform.e,
        "width": width,
        "height": height,
        "classes": {
            "30": "şehir merkezi", "23": "yoğun kentsel küme", "22": "kasaba",
            "21": "şehir çeperi", "13": "köy", "12": "seyrek kırsal",
            "11": "çok seyrek kırsal", "10": "nüfussuz",
        },
        "source": "WorldPop 2020 (CC BY 4.0), 1 km — Degree of Urbanisation eşikleriyle sınıflandırıldı",
        "built": date.today().isoformat(),
    }
    header_bytes = json.dumps(header, ensure_ascii=False).encode("utf-8")
    payload = struct.pack("<4sI", b"DGX1", len(header_bytes)) + header_bytes + classes.tobytes() + density.tobytes()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(gzip.compress(payload, 9))
    print(f"yazıldı: {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size / 1e6:.2f} MB)")

    names = header["classes"]
    for code in (30, 23, 22, 21, 13, 12, 11):
        cells = int((classes == code).sum())
        people = float(population[classes == code].sum())
        print(f"  {names[str(code)]:<20} {cells:>7,} hücre  {people / 1e6:>6.2f} milyon kişi")

    print("\nörnek noktalar:")
    samples = [
        ("İstanbul Kadıköy", 40.9900, 29.0300),
        ("Ankara Kızılay", 39.9208, 32.8541),
        ("Bursa Nilüfer", 40.2140, 28.9157),
        ("Bursa Mudanya", 40.3752, 28.8838),
        ("Samsun Alaçam merkez", 41.6056, 35.5981),
        ("Alaçam Aşağıkoçlu köyü", 41.5719, 35.5110),
    ]
    for label, lat, lng in samples:
        column = int((lng - header["west"]) / header["res_lng"])
        row = int((header["north"] - lat) / header["res_lat"])
        code = int(classes[row, column])
        print(f"  {label:<26} {names[str(code)]:<20} {population[row, column]:>8.0f} kişi/km²")


if __name__ == "__main__":
    main()
