"""Ölçüm: parselin yerleşik alana uzaklığı, ilan fiyatını açıklıyor mu?

Modelin bugünkü en büyük hataları imarsız arazide: kâğıtta "tarla", piyasada imar
beklentisi olan parseller ilanda modelin 7-9 katını istiyor. Model bunu parsel
büyüklüğü ve yerleşim merkezine uzaklık kapılarıyla tahmin etmeye çalışıyor ve
tutturamıyor. Bu betik başka bir sinyali deniyor: OSM'de çizilmiş yerleşik alan
poligonuna (landuse=residential/commercial/industrial/retail) uzaklık ve 400 m
içindeki bina sayısı. İkisi de kullanıcıya soru sormadan, koordinattan okunur.

Çıktı: her ilan için uzaklık + bina sayısı + ilanın modele oranı, sonra kova
bazında ortanca oran. Karar bu tabloya bakılarak verilir; betik modeli değiştirmez.

    python -P tools/yerlesim_olc.py            # Overpass'a sorar, CSV yazar
    python -P tools/yerlesim_olc.py --cache    # yazılmış CSV'yi yeniden özetler
"""

import asyncio
import csv
import math
import statistics
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "tools"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx  # noqa: E402

import ilan_karsilastir as karsilastir  # noqa: E402
from app import market, urbanity  # noqa: E402
from app.geo import distance_to_line_m  # noqa: E402
from app.valuation import estimate, load_parameters  # noqa: E402
from olcum_ortak import hedef_tl  # noqa: E402

CIKTI = ROOT_DIR / "data" / "private" / "ciktilar" / "yerlesim_olcum.csv"
# Ana Overpass ornegi gun icinde 40 s'ye kadar yavasliyor, zaman zaman 502 veriyor;
# ayni sorgu Fransa aynasinda 8 s suruyor. Sirayla denenir.
OVERPASS = ("https://overpass.openstreetmap.fr/api/interpreter",
            "https://overpass-api.de/api/interpreter")
USER_AGENT = "Degerix/4.0 (arsa degerleme portfolyo projesi)"
YERLESIM_YARICAP_M = 3000   # bu kadar uzakta poligon yoksa "uzak" sayilir
BINA_YARICAP_M = 400
BEKLE_S = 1.0               # Overpass adil kullanim
IMARLI = {"konut", "ticari", "sanayi"}

SORGU = """[out:json][timeout:30];
way["landuse"~"^(residential|commercial|industrial|retail)$"](around:{yaricap},{lat},{lng});
out geom;
way["building"](around:{bina},{lat},{lng});
out count;"""


def icinde(lat: float, lng: float, halka: list[tuple[float, float]]) -> bool:
    """Isin atma: nokta poligonun icinde mi (parsel yerlesik alanin icinde mi)."""
    sayac = 0
    for (y1, x1), (y2, x2) in zip(halka, halka[1:] + halka[:1]):
        if (y1 > lat) != (y2 > lat):
            kesim = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if kesim > lng:
                sayac += 1
    return sayac % 2 == 1


def coz(veri: dict, lat: float, lng: float) -> tuple[float, str, int]:
    """Overpass yaniti -> (yerlesik alana m, poligon turu, bina sayisi)."""
    en_yakin, tur, bina = math.inf, "", 0
    for eleman in veri.get("elements", []):
        if eleman.get("type") == "count":
            bina = int((eleman.get("tags") or {}).get("ways", 0))
            continue
        geom = eleman.get("geometry") or []
        if len(geom) < 3:
            continue
        halka = [(n["lat"], n["lon"]) for n in geom if n]
        kullanim = (eleman.get("tags") or {}).get("landuse", "")
        uzaklik = 0.0 if icinde(lat, lng, halka) else distance_to_line_m(lat, lng, halka)
        if uzaklik < en_yakin:
            en_yakin, tur = uzaklik, kullanim
    return (en_yakin if math.isfinite(en_yakin) else float(YERLESIM_YARICAP_M * 2)), tur, bina


async def olc(istemci: httpx.AsyncClient, lat: float, lng: float) -> tuple[float, str, int]:
    sorgu = SORGU.format(yaricap=YERLESIM_YARICAP_M, bina=BINA_YARICAP_M,
                         lat=f"{lat:.6f}", lng=f"{lng:.6f}")
    for deneme in range(3):
        for adres in OVERPASS:
            try:
                yanit = await istemci.post(adres, data={"data": sorgu})
                yanit.raise_for_status()
                return coz(yanit.json(), lat, lng)
            except (httpx.HTTPError, ValueError):
                continue
        await asyncio.sleep(5 * (deneme + 1))
    raise RuntimeError("Overpass yanit vermedi")


def kova(m: float) -> str:
    if m <= 0:
        return "1 icinde"
    if m <= 150:
        return "2 0-150 m"
    if m <= 500:
        return "3 150-500 m"
    if m <= 1500:
        return "4 500-1500 m"
    return "5 1500 m+"


def ozetle(satirlar: list[dict]) -> None:
    def rapor(ad: str, grup: list[dict]) -> None:
        if not grup:
            print(f"  {ad:14} -")
            return
        oranlar = [s["oran"] for s in grup]
        log = statistics.mean(abs(math.log2(o)) for o in oranlar)
        binalar = statistics.median([s["bina"] for s in grup])
        print(f"  {ad:14} n={len(grup):3}  medyan={statistics.median(oranlar):5.2f}  "
              f"ort|log2|={log:4.2f}  ortanca bina={int(binalar):4}")

    for baslik, sart in (("TUM ILANLAR", lambda s: True),
                         ("IMARSIZ (tarla/bag/bahce)", lambda s: s["imarsiz"] == "1"),
                         ("IMARLI (konut/ticari)", lambda s: s["imarsiz"] == "0"),
                         ("IMARSIZ - parsel pinli", lambda s: s["imarsiz"] == "1" and s["konum"] == "parsel")):
        grup = [s for s in satirlar if sart(s)]
        print(f"\n== {baslik} (n={len(grup)}) ==  (oran = ilan / model; 1,00 isabet)")
        for ad in sorted({s["kova"] for s in grup}):
            rapor(ad, [s for s in grup if s["kova"] == ad])

    print("\n== BINA YOGUNLUGU (400 m icinde, imarsiz) ==")
    imarsiz = [s for s in satirlar if s["imarsiz"] == "1"]
    for ad, alt, ust in (("0 bina", 0, 0), ("1-10", 1, 10), ("11-50", 11, 50),
                         ("51-200", 51, 200), ("200+", 201, 10**9)):
        grup = [s for s in imarsiz if alt <= s["bina"] <= ust]
        if grup:
            oranlar = [s["oran"] for s in grup]
            print(f"  {ad:8} n={len(grup):3}  medyan={statistics.median(oranlar):5.2f}")


async def main() -> None:
    if "--cache" in sys.argv:
        satirlar = list(csv.DictReader(CIKTI.open(encoding="utf-8")))
        for s in satirlar:
            s["oran"], s["bina"] = float(s["oran"]), int(s["bina"])
        ozetle(satirlar)
        return

    kayitlar = [k for k in karsilastir.oku() if not k["haric"]]
    indirim = load_parameters().asking_discount
    print(f"{len(kayitlar)} kayit - Overpass'a sorulacak "
          f"(yaklasik {len(kayitlar) * (BEKLE_S + 2) / 60:.0f} dk)\n")
    satirlar: list[dict] = []
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=40) as istemci:
        for sira, k in enumerate(kayitlar, 1):
            try:
                yer = urbanity.describe(k["lat"], k["lng"])
                if yer is None:
                    continue
                housing = await market.housing_price(k["il"])
                e = estimate(area_m2=k["alan"], usage=k["usage"], housing=housing, urban=yer,
                             surroundings=None, kaks=k["kaks"], **k["cevaplar"])
                uzaklik, tur, bina = await olc(istemci, k["lat"], k["lng"])
            except Exception as hata:                              # noqa: BLE001
                print(f"  {sira}/{len(kayitlar)} {k['etiket']}: {type(hata).__name__}: {hata}")
                continue
            # Hedef, ilanin kendisi degil pazarlik payi dusulmus fiyat; calibrate.py
            # ve ilan_karsilastir.py ile ayni hedef, yoksa oranlar kiyaslanamaz.
            hedef = hedef_tl(k["deger"], k["tur"], indirim)
            if hedef is None:
                print(f"  {sira}/{len(kayitlar)} {k['etiket']}: bilinmeyen deger_turu, olcum disi")
                continue
            hedef /= k["alan"]
            satirlar.append(dict(
                il=k["il"], ilce=k["ilce"], konum=k["konum"], imar=k["usage"],
                alan=int(k["alan"]), ilan_tl_m2=round(k["deger"] / k["alan"]),
                model_tl_m2=e.unit_price, oran=round(hedef / e.unit_price, 3),
                yerlesim_m=round(uzaklik), yerlesim_turu=tur, bina=bina,
                kova=kova(uzaklik), imarsiz="0" if k["usage"] in IMARLI else "1",
                lat=k["lat"], lng=k["lng"]))
            print(f"  {sira}/{len(kayitlar)} {k['etiket']:22} {k['usage']:8} "
                  f"yerlesik={round(uzaklik):5} m bina={bina:4} oran={satirlar[-1]['oran']:5.2f}",
                  flush=True)
            await asyncio.sleep(BEKLE_S)

    if not satirlar:
        print("Olculebilir kayit yok.")
        return
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    with CIKTI.open("w", encoding="utf-8", newline="") as dosya:
        yazici = csv.DictWriter(dosya, fieldnames=list(satirlar[0]))
        yazici.writeheader()
        yazici.writerows(satirlar)
    print(f"\nCSV: {CIKTI}")
    ozetle(satirlar)


if __name__ == "__main__":
    asyncio.run(main())
