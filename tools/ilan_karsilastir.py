"""Gerçek arsa ilanlarını Değerix'in emsalsiz tahminiyle karşılaştırır.

Ölçümdür, kalibrasyon değil: hiçbir katsayı değiştirilmez. Veri `data/private/`
altındaki CSV'lerden okunur (şema: data/pilot/bursa.csv ile aynı); o klasör
gitignore'da olduğu için ilan verisi yayımlanmaz.

    python tools/ilan_karsilastir.py            # özet
    python tools/ilan_karsilastir.py --detay    # her ilan için satır
    python tools/ilan_karsilastir.py --cevre    # çevre düzeltmeleriyle (yavaş)

Varsayılan ölçüm çevre düzeltmelerini (OSM yol/hizmet/kıyı + eğim) GEÇMEZ, çünkü
her kayıt için Overpass sorgusu gerekir ve ölçüm dakikalarca sürer. Farkı ölçtük:
84 ilanda çevre çarpanının ortancası 0,984 ve en yükseği 1,000 — yani bu modül
yalnızca indirim uyguluyor, hiç prim vermiyor. Sonuç olarak parsel pinli kümede
tipik hata 0,94'ten 0,96'ya ÇIKIYOR: model zaten hafif düşükken bir indirim daha
biniyor. Bu yüzden `--cevre` isteğe bağlıdır ama uygulamanın kullanıcıya verdiği
cevap onu içerir; aradaki fark buradaki rakamların yaklaşık %1,6'sıdır.
"""

import asyncio
import csv
import math
import statistics
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# load_dotenv yalnızca app/main.py'de çağrılıyor; betik uygulamayı ayağa kaldırmadığı
# için anahtarı kendisi yüklemeli, yoksa EVDS devre dışı kalıp ölçüm sessizce
# konut fiyatı kopyasına düşer ve tablo eski veriyle çıkar.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT_DIR / ".env")

from app import market, nearby, urbanity  # noqa: E402
from app.valuation import estimate, load_parameters  # noqa: E402

VERI_DIZINI = ROOT_DIR / "data" / "private"
IMARLI = {"konut", "ticari", "sanayi"}
BUYUK_M2 = 5000
# Tapu/yol/elektrik gibi alanlar boşsa modele hiç geçilmez: estimate bunları
# "bilinmiyor" sayar ve nötr bırakır, boş dizeyi geçersek doğrulama hatası verir.
CEVAP_ALANLARI = {"tapu": "deed", "yol": "road", "elektrik_su": "utilities",
                  "manzara": "view", "kose": "corner", "sulama": "irrigation"}


def sayi(metin: str) -> float | None:
    """CSV'de iki yazım bir arada: "12.700.000" (binlik nokta) ve "41.137" (ondalık nokta).

    Ayrım virgülden gelir: virgül varsa nokta binlik ayracıdır, yoksa ondalık
    ayracıdır. Noktayı koşulsuz silmek koordinatı 41.137 -> 41137 yapıp parseli
    Türkiye'nin dışına taşıyor ve ölçüm sessizce boş çıkıyordu.
    """
    metin = (metin or "").strip()
    metin = metin.replace(".", "").replace(",", ".") if "," in metin else metin
    try:
        return float(metin)
    except ValueError:
        return None


def oku() -> list[dict]:
    kayitlar = []
    for yol in sorted(VERI_DIZINI.glob("*.csv")):
        for satir in csv.DictReader(yol.open(encoding="utf-8")):
            lat, lng = sayi(satir.get("lat", "")), sayi(satir.get("lng", ""))
            alan, deger = sayi(satir.get("alan_m2", "")), sayi(satir.get("deger_tl", ""))
            if None in (lat, lng, alan, deger) or not alan or not satir.get("imar", "").strip():
                continue
            # Yalnızca gerçek ilan/satış kaydı ölçüme girer. Bu kontrol olmadan
            # data/private altına yazılan bir MODEL ÇIKTISI (ör. toplu_degerle.py
            # sonucu) ilan sanılıp okunuyor ve model kendi tahminine karşı
            # ölçülüyordu: 84 kayıt bir anda 101 olup hata sahte biçimde düşüyordu.
            if satir.get("deger_turu", "").strip() not in ("ilan", "satis"):
                continue
            cevaplar = {ad: satir[sutun].strip() for sutun, ad in CEVAP_ALANLARI.items()
                        if satir.get(sutun, "").strip()}
            kayitlar.append(dict(
                kaynak=yol.stem, il=satir["il"].strip(),
            # Koordinat hassasiyeti: "parsel" gerçek pin, "mahalle" ise mahalle
            # merkezi. İkincisinde yerleşime uzaklık, kentsellik sınıfı ve
            # erişilebilirlik parselin değil yerleşimin ölçümüdür; mesafeye
            # duyarlı mekanizmalar o kayıtlara göre ayarlanamaz.
            konum=satir.get("konum", "").strip() or "?",
                ilce=satir["ilce"].strip() or "?",
                etiket=f"{satir['il'].strip()}/{satir['ilce'].strip() or '?'}",
                lat=lat, lng=lng, alan=alan, deger=deger,
                usage=satir["imar"].strip(), kaks=sayi(satir.get("emsal", "")),
                haric=satir.get("haric", "").strip(), cevaplar=cevaplar))
    return kayitlar


def med(degerler):
    return statistics.median(degerler) if degerler else float("nan")


def ozet(ad: str, grup: list[dict]) -> str:
    if not grup:
        return f"{ad:34} -"
    oranlar = [s["oran"] for s in grup]
    # Oran çarpımsal bir hata: log2 ortalaması 2 kat aşağı ile 2 kat yukarıyı eşit sayar,
    # düz ortalama ise yukarı sapmaları ağırlıklandırıp tabloyu yanıltır.
    log_hata = statistics.mean(abs(math.log2(s["oran"])) for s in grup)
    return (f"{ad:34} n={len(grup):3}  medyan={med(oranlar):5.2f}  "
            f"ort|log2|={log_hata:4.2f}  ±%50 içinde={sum(abs(o - 1) <= 0.5 for o in oranlar)}/{len(grup)}")


async def main() -> None:
    detay = "--detay" in sys.argv
    cevreli = "--cevre" in sys.argv
    kayitlar = oku()
    if not kayitlar:
        print(f"{VERI_DIZINI} altında koordinatlı ilan bulunamadı.")
        return

    indirim = load_parameters().asking_discount
    satirlar, hatalar = [], []
    for k in kayitlar:
        try:
            housing = await market.housing_price(k["il"])
            yer = urbanity.describe(k["lat"], k["lng"])
            if yer is None:
                hatalar.append(f"{k['etiket']}: kentsellik ızgarasının dışında")
                continue
            cevre = await nearby.fetch(k["lat"], k["lng"]) if cevreli else None
            e = estimate(area_m2=k["alan"], usage=k["usage"], housing=housing, urban=yer,
                         surroundings=cevre, kaks=k["kaks"], **k["cevaplar"])
        except Exception as hata:                                  # noqa: BLE001
            hatalar.append(f"{k['etiket']}: {type(hata).__name__}: {hata}")
            continue
        # Hedef ilan fiyatının kendisi değil: ilan, satışın üstünde durur. Model
        # gerçekleşen satışı tahmin ettiği için karşılaştırma da pazarlık payı
        # düşülmüş fiyata yapılır — tools/calibrate.py ile aynı hedef.
        hedef = k["deger"] * (1 - indirim)
        hedef_m2 = hedef / k["alan"]
        satirlar.append(dict(k, e=e, ilan=hedef_m2, model=e.unit_price,
                             oran=hedef_m2 / e.unit_price, yer=yer,
                             kapsar=e.low <= hedef <= e.high))

    kaynaklar = sorted({s["kaynak"] for s in satirlar})
    print(f"Veri: {', '.join(kaynaklar)} · {len(satirlar)} ilan · {len(kayitlar) - len(satirlar)} atlandı")
    print(f"Konut fiyatı: {await _canli_mi()}")
    print(f"Hedef: ilan fiyatı × {1 - indirim:.2f} (pazarlık payı %{indirim * 100:.0f})\n")

    gecerli = [s for s in satirlar if not s["haric"]]
    print("== GRUPLAR (haric işaretli ilanlar dışarıda) ==")
    print(ozet("Tümü", gecerli))
    print(ozet("  İmarlı (konut/ticari/sanayi)", [s for s in gecerli if s["usage"] in IMARLI]))
    print(ozet("  İmarsız (tarla/bağ/zeytin)", [s for s in gecerli if s["usage"] not in IMARLI]))
    print(ozet("  Küçük parsel (<5 dönüm)", [s for s in gecerli if s["alan"] < BUYUK_M2]))
    print(ozet("  Büyük parsel (≥5 dönüm)", [s for s in gecerli if s["alan"] >= BUYUK_M2]))
    print(ozet("Koordinat parselin kendisi", [s for s in gecerli if s["konum"] == "parsel"]))
    print(ozet("  bunların imarsızları", [s for s in gecerli if s["konum"] == "parsel" and s["usage"] not in IMARLI]))
    print(ozet("Koordinat mahalle merkezi", [s for s in gecerli if s["konum"] == "mahalle"]))
    print(ozet("Haric işaretliler dahil hepsi", satirlar))

    print("\n== İL BAZINDA ==")
    for il in sorted({s["il"] for s in gecerli}):
        grup = [s for s in gecerli if s["il"] == il]
        print(f"  {il:12} n={len(grup):2}  medyan oran={med([s['oran'] for s in grup]):5.2f}  "
              f"oranlar={' '.join(f'{s["oran"]:.2f}' for s in sorted(grup, key=lambda s: s['oran']))}")

    # İlçe tablosu, ilin ortalamasıyla fiyatlamanın bedelini gösterir: TCMB il
    # başına tek bir konut fiyatı yayımlıyor, oysa aynı ilin iki ilçesi arasında
    # arsa fiyatı kat kat ayrışıyor. Sapma ilçe içinde tutarlıysa sorun modelin
    # mekanizmasında değil, elindeki fiyat verisinin çözünürlüğündedir.
    print("\n== İLÇE BAZINDA (en az 2 ilan, en sapmalı önce) ==")
    print(f"  {'ilçe':24} {'n':>2} {'ilan ₺/m²':>10} {'model ₺/m²':>10} {'oran':>6}  yöntem")
    ilceler = []
    for anahtar in {(s["il"], s["ilce"]) for s in gecerli}:
        grup = [s for s in gecerli if (s["il"], s["ilce"]) == anahtar]
        if len(grup) >= 2:
            ilceler.append((anahtar, grup, med([s["oran"] for s in grup])))
    for (il, ilce), grup, oran in sorted(ilceler, key=lambda satir: -abs(math.log2(satir[2]))):
        yontemler = sorted({s["e"].basis for s in grup})
        print(f"  {il + '/' + ilce:24} {len(grup):>2} {med([s['ilan'] for s in grup]):>10,.0f} "
              f"{med([s['model'] for s in grup]):>10,.0f} {oran:>6.2f}  {'+'.join(yontemler)}")

    print("\n== EN KÖTÜ 10 (|log2 oran|) ==")
    print(f"  {'etiket':24} {'imar':10} {'alan':>7} {'ilan ₺/m²':>10} {'model ₺/m²':>10} {'oran':>5}  sınıf · yöntem")
    for s in sorted(gecerli, key=lambda s: -abs(math.log2(s["oran"])))[:10]:
        print(f"  {s['etiket'][:24]:24} {s['usage']:10} {s['alan']:>7.0f} {s['ilan']:>10,.0f} "
              f"{s['model']:>10,.0f} {s['oran']:>5.2f}  {s['yer'].class_code}/{s['e'].settlement[:22]} · {s['e'].basis}")

    print(f"\nModel aralığı ilan fiyatını kapsıyor: {sum(s['kapsar'] for s in gecerli)}/{len(gecerli)}")
    if hatalar:
        print("\n== HESAPLANAMAYAN ==")
        for satir in hatalar:
            print("  " + satir)

    if detay:
        print("\n== TÜM İLANLAR ==")
        for s in sorted(satirlar, key=lambda s: s["oran"]):
            print(f"  {s['etiket'][:24]:24} {s['usage']:10} {s['alan']:>8.0f} "
                  f"{s['ilan']:>10,.0f} {s['model']:>10,.0f} {s['oran']:>5.2f} "
                  f"{'[' + s['haric'] + ']' if s['haric'] else ''}")


async def _canli_mi() -> str:
    fiyat = await market.housing_price("İstanbul")
    return f"{fiyat.live} · {fiyat.period} · {fiyat.source}"


if __name__ == "__main__":
    asyncio.run(main())
