"""Değer aralığını ölçülen hataya oturtur — doğru sırayla.

    python tools/bant_kalibre.py                  # rapor
    python tools/bant_kalibre.py --hedef 0.80     # başka kapsama hedefi
    python tools/bant_kalibre.py --uygula         # model_params.py'yi günceller

Yöntem, Codex incelemesinde üzerinde anlaşılan sıradır ve sırası önemlidir:

  1. Önce aralığın NE İÇİN olduğuna karar verilir: "ilanların %80'ini kapsasın".
     Ortalama mutlak log hata bir kapsama hedefi belirlemez; hedef bir üründür,
     ölçümün sonucu değil.
  2. Yayılım, AYRILMIŞ bir kalibrasyon kümesinde mutlak log hatanın o
     yüzdeliğinden hesaplanır. Aynı kayıtlarda hem kurup hem ölçmek, kapsamayı
     olduğundan iyi gösterir — kayıt kendi bandını kurmuş olur.
  3. Kapsama ve bant genişliği, kurulumda hiç görülmemiş bir test kümesinde,
     imar grubuna göre BİRLİKTE raporlanır. Yalnız kapsama bakmak yanıltır:
     yayılımı büyüterek kapsama %100 yapılabilir, ama aralık işe yaramaz.

104 kayıt tek bir ayırma için az olduğundan K katlı çapraz doğrulama
kullanılıyor: her kat sırayla test olur, yayılım diğer katlardan kurulur,
sonuçlar ortalanır. Böylece her kayıt tam bir kez "görülmemiş" olarak ölçülür.

Yayılım kaydın tamamına değil, hesaplama tabanına (gelistirme / taban / arazi /
beklenti) göre kurulur, çünkü model bunları farklı bilgiyle hesaplıyor. Ayrıca
bandın taban payı dışında kayda özel ekler var (emsal, çevre ölçülememesi,
yanıtlanmamış soru); bunlar kaydın kendi ekidir ve hesaptan düşülür, yoksa
taban payı onların üstüne ikinci kez binerdi.
"""

import argparse
import asyncio
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app import market, urbanity  # noqa: E402
from app.surroundings import OsmContext, Surroundings  # noqa: E402
from app.valuation import estimate, load_parameters  # noqa: E402
from ilan_karsilastir import oku  # noqa: E402
from olcum_ortak import hedef_tl  # noqa: E402

KATLAR = 5
TOHUM = 20261126   # kat dağılımı yeniden üretilebilsin
CEVRE_CSV = ROOT / "data" / "private" / "ciktilar" / "cevre_olcum.csv"


def _sayi(metin: str):
    metin = (metin or "").strip()
    return float(metin) if metin else None


def cevre_olcumleri() -> dict[tuple[float, float], Surroundings]:
    """Daha önce toplanmış çevre ölçümlerini koordinata göre yükler.

    Bu şart, süs değil: çevre ölçümü olmadan koşulursa her imarsız kayda
    "çevre ölçülemedi" bant genişlemesi biniyor (fringe_premium − 1 = +1,00)
    ve ölçüm, üretimde nadiren görülen bir en kötü hâli kalibre etmiş oluyor.
    Dosya tools/cevre_olc.py --topla ile üretiliyor.
    """
    if not CEVRE_CSV.exists():
        return {}
    import csv
    olcum = {}
    for satir in csv.DictReader(CEVRE_CSV.open(encoding="utf-8")):
        try:
            anahtar = (round(float(satir["lat"]), 5), round(float(satir["lng"]), 5))
        except (KeyError, TypeError, ValueError):
            continue
        olcum[anahtar] = Surroundings(
            osm=OsmContext(
                coast_m=_sayi(satir.get("coast_m")),
                main_road_m=_sayi(satir.get("main_road_m")),
                services=int(_sayi(satir.get("services")) or 0),
                buildings=int(_sayi(satir.get("buildings")) or 0),
                built_up_m=_sayi(satir.get("built_up_m")),
            ),
            slope_pct=_sayi(satir.get("slope_pct")),
        )
    return olcum


def yuzdelik(degerler: list[float], oran: float) -> float:
    """Sıralı listede oran yüzdeliği (doğrusal aradeğerleme).

    statistics.quantiles sabit sayıda kesim noktası veriyor; burada tek ve
    serbest bir yüzdelik gerekiyor.
    """
    if not degerler:
        return 0.0
    sirali = sorted(degerler)
    if len(sirali) == 1:
        return sirali[0]
    yer = oran * (len(sirali) - 1)
    alt = math.floor(yer)
    ust = math.ceil(yer)
    if alt == ust:
        return sirali[alt]
    return sirali[alt] + (sirali[ust] - sirali[alt]) * (yer - alt)


async def kayitlari_olc() -> list[dict]:
    """Her kayıt için modeli çalıştırır ve bandın bileşenlerini ayırır."""
    p = load_parameters()
    indirim = p.asking_discount
    cevreler = cevre_olcumleri()
    satirlar, atlanan, haric, cevresiz, mahalle = [], 0, 0, 0, 0
    for k in oku():
        # "haric" işaretli kayıtlar (yapılı parsel, spekülatif fiyat) dosyada
        # kalır ama ölçüme girmez; ilan_karsilastir.py da böyle yapıyor.
        # Bant kalibrasyonu da aynı kümede olmalı, yoksa iki araç farklı
        # sayılar üretir ve hangisinin doğru olduğu belirsiz kalır.
        if k.get("haric"):
            haric += 1
            continue
        # Koordinatı mahalle merkezi olan kayıtlar da dışarıda. Üretimde böyle
        # bir istek olmuyor: kullanıcı haritada parselin üstüne tıklıyor ya da
        # ada/parsel giriyor, iki yolda da koordinat parselin kendisi. O
        # kayıtlarda model köy çekirdeğinin yerleşim sınıfıyla fiyatlandırılıyor
        # ve hata parselin değil koordinatın hatası oluyor. Bandı onlarla
        # kurmak, üretimde hiç görülmeyen bir hatayı kullanıcının aralığına
        # yazmak demek. (Ölçülen fark büyük: imarlı kayıtlarda ortanca oran
        # parsel koordinatıyla 0,944, mahalle koordinatıyla 0,550.)
        if (k.get("konum") or "").strip() != "parsel":
            mahalle += 1
            continue
        try:
            housing = await market.housing_price(k["il"])
            yer = urbanity.describe(k["lat"], k["lng"])
            if yer is None:
                atlanan += 1
                continue
            cevre = cevreler.get((round(k["lat"], 5), round(k["lng"], 5)))
            if cevre is None:
                cevresiz += 1
            e = estimate(area_m2=k["alan"], usage=k["usage"], housing=housing, urban=yer,
                         surroundings=cevre, kaks=k["kaks"], **k["cevaplar"])
        except Exception:                                          # noqa: BLE001
            atlanan += 1
            continue
        hedef = hedef_tl(k["deger"], k["tur"], indirim)
        if hedef is None or e.total <= 0:
            atlanan += 1
            continue

        # Bandın bugünkü toplam yayılımı ve bunun taban dışı kısmı.
        # high = total * (1 + yayilim) olduğundan yayılım doğrudan okunur.
        yayilim = e.high / e.total - 1
        taban_payi = p.basis_spread[e.basis]
        ek = max(yayilim - taban_payi, 0.0)       # emsal, çevre, yanıtsız soru ekleri

        oran = hedef / e.total
        satirlar.append({
            "etiket": k["etiket"],
            "taban": e.basis,
            "imarli": k["usage"] in ("konut", "ticari", "sanayi"),
            "log_hata": abs(math.log2(oran)),
            "ek": ek,
            "oran": oran,
        })
    if atlanan or haric or mahalle:
        print(f"({haric} kayıt 'haric' işaretli, {mahalle} kayıt mahalle merkezi "
              f"koordinatlı, {atlanan} kayıt eksik veri — ölçüme girmedi)")
    if cevresiz:
        print(f"UYARI: {cevresiz} kaydın çevre ölçümü yok; o kayıtlarda bant "
              f"'çevre ölçülemedi' genişlemesini taşıyor ve yayılım olduğundan geniş ölçülür.")
    return satirlar


def gereken_taban_payi(satir: dict) -> float:
    """Bu kaydın kapsanması için taban payının en az ne olması gerektiği.

    |log2 oran| <= log2(1 + yayılım) koşulundan yayılım çözülür, kaydın kendi
    ekleri düşülür. Negatifse sıfır: kayıt eklerle zaten kapsanıyor demektir.
    """
    return max(2 ** satir["log_hata"] - 1 - satir["ek"], 0.0)


def katlara_ayir(satirlar: list[dict], k: int) -> list[list[dict]]:
    karisik = list(satirlar)
    random.Random(TOHUM).shuffle(karisik)
    return [karisik[i::k] for i in range(k)]


def capraz_dogrula(satirlar: list[dict], hedef: float) -> dict:
    """K katlı: her katta yayılım diğer katlardan kurulur, o katta ölçülür."""
    katlar = katlara_ayir(satirlar, KATLAR)
    sonuc = []
    for i, test in enumerate(katlar):
        egitim = [s for j, kat in enumerate(katlar) if j != i for s in kat]
        paylar = {}
        for taban in {s["taban"] for s in egitim}:
            gereken = [gereken_taban_payi(s) for s in egitim if s["taban"] == taban]
            paylar[taban] = yuzdelik(gereken, hedef)
        varsayilan = yuzdelik([gereken_taban_payi(s) for s in egitim], hedef)
        for s in test:
            pay = paylar.get(s["taban"], varsayilan)
            yayilim = pay + s["ek"]
            sonuc.append({
                **s,
                "kapsandi": s["log_hata"] <= math.log2(1 + yayilim),
                "genislik": (1 + yayilim) ** 2,   # üst/alt oranı
            })
    return {"satirlar": sonuc}


def paylari_kur(satirlar: list[dict], hedef: float) -> dict[str, float]:
    """Tüm veriyle son yayılımlar (yayımlanacak değerler)."""
    paylar = {}
    for taban in sorted({s["taban"] for s in satirlar}):
        gereken = [gereken_taban_payi(s) for s in satirlar if s["taban"] == taban]
        paylar[taban] = round(yuzdelik(gereken, hedef), 2)
    return paylar


def rapor(satirlar: list[dict], hedefler: list[float]) -> None:
    p = load_parameters()
    print(f"\n{len(satirlar)} kayıt · {KATLAR} katlı çapraz doğrulama · tohum {TOHUM}")
    print("Yayılım her katta diğer katlardan kurulur, o katta hiç görülmemiş kayıtlarda ölçülür.\n")

    print(f"{'hedef':>6} {'grup':<22} {'n':>4} {'kapsama':>9} {'ort. genişlik':>14}")
    print("-" * 60)
    for hedef in hedefler:
        olculen = capraz_dogrula(satirlar, hedef)["satirlar"]
        gruplar = [("tümü", olculen),
                   ("imarlı", [s for s in olculen if s["imarli"]]),
                   ("imarsız", [s for s in olculen if not s["imarli"]])]
        for ad, grup in gruplar:
            if not grup:
                continue
            kapsama = sum(s["kapsandi"] for s in grup) / len(grup)
            genislik = statistics.median(s["genislik"] for s in grup)
            print(f"{hedef:>6.0%} {ad:<22} {len(grup):>4} {kapsama:>8.0%} {genislik:>13.1f}×")
        print()

    print("Bugünkü yayılımlar ve hedeflere göre önerilenler:")
    print(f"{'taban':<14} {'bugün':>7}" + "".join(f"{h:>9.0%}" for h in hedefler))
    oneriler = {h: paylari_kur(satirlar, h) for h in hedefler}
    for taban in sorted(p.basis_spread):
        satir = f"{taban:<14} {p.basis_spread[taban]:>7.2f}"
        for h in hedefler:
            satir += f"{oneriler[h].get(taban, float('nan')):>9.2f}"
        n = sum(1 for s in satirlar if s["taban"] == taban)
        print(satir + f"   (n={n})")

    print("\nBugünkü yayılımların aynı çapraz doğrulamadaki karşılığı:")
    bugun = []
    for s in satirlar:
        yayilim = p.basis_spread[s["taban"]] + s["ek"]
        bugun.append({**s, "kapsandi": s["log_hata"] <= math.log2(1 + yayilim),
                      "genislik": (1 + yayilim) ** 2})
    for ad, grup in [("tümü", bugun), ("imarlı", [s for s in bugun if s["imarli"]]),
                     ("imarsız", [s for s in bugun if not s["imarli"]])]:
        if not grup:
            continue
        kapsama = sum(s["kapsandi"] for s in grup) / len(grup)
        genislik = statistics.median(s["genislik"] for s in grup)
        print(f"  {ad:<22} {len(grup):>4} {kapsama:>8.0%} {genislik:>13.1f}×")

    print("\nSeviye kayması (ortanca oran; 1,00 = model doğru seviyede):")
    for ad, grup in [("tümü", satirlar), ("imarlı", [s for s in satirlar if s["imarli"]]),
                     ("imarsız", [s for s in satirlar if not s["imarli"]])]:
        if grup:
            print(f"  {ad:<22} {len(grup):>4} {statistics.median(s['oran'] for s in grup):>8.2f}")
    for taban in sorted({s["taban"] for s in satirlar}):
        grup = [s for s in satirlar if s["taban"] == taban]
        print(f"    {taban:<20} {len(grup):>4} {statistics.median(s['oran'] for s in grup):>8.2f}")


def uygula(paylar: dict[str, float], hedef: float) -> None:
    yol = ROOT / "app" / "model_params.py"
    metin = yol.read_text(encoding="utf-8")
    for taban, deger in paylar.items():
        import re
        desen = re.compile(rf'("{taban}":\s*)([0-9.]+)(,)')
        if not desen.search(metin):
            print(f"  UYARI: {taban} satırı bulunamadı, elle güncelleyin")
            continue
        metin = desen.sub(rf'\g<1>{deger:.2f}\g<3>', metin, count=1)
    yol.write_text(metin, encoding="utf-8")
    print(f"\napp/model_params.py güncellendi (hedef kapsama {hedef:.0%}): {paylar}")


async def main() -> None:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--hedef", type=float, default=None,
                             help="tek bir kapsama hedefi (ör. 0.80)")
    ayristirici.add_argument("--uygula", action="store_true",
                             help="--hedef ile seçilen yayılımları model_params.py'ye yazar")
    secenek = ayristirici.parse_args()

    satirlar = await kayitlari_olc()
    if not satirlar:
        print("Ölçülebilir kayıt yok.")
        return

    hedefler = [secenek.hedef] if secenek.hedef else [0.70, 0.80, 0.90]
    rapor(satirlar, hedefler)

    if secenek.uygula:
        if secenek.hedef is None:
            print("\n--uygula için --hedef şart: hangi kapsamayı istediğinizi seçin.")
            return
        uygula(paylari_kur(satirlar, secenek.hedef), secenek.hedef)


if __name__ == "__main__":
    asyncio.run(main())
