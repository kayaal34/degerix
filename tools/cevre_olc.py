"""Ölçüm: çevre modülünün dört katsayısı (kıyı, ana yol, hizmet, eğim) doğru mu?

Bu dört katsayı projeye ölçülmeden, makul görünen değerlerle girdi. Kıyı primi
ölçülürken yapılan kontrol koşusu şunu gösterdi: modül açıkken 1,5 kat içindeki kayıt
63'ten 57'ye düşüyor, ortanca oran 0,96'dan 1,07'ye çıkıyor — yani dördü birlikte
değeri sistematik olarak aşağı çekiyor. Sebebi anlaşılır: "ana yol 1,5 km içinde
yoksa ×0,90", "hizmet yoksa ×0,95" gibi varsayımlar hiç prim vermiyor, yalnızca
kırpıyor; Türkiye kırsalında OSM'de yol çizilmemiş olması parselin yolu olmadığı
anlamına gelmiyor, biz eksik veriyi fiyat indirimi sayıyoruz.

Yöntem: her ilan için çevre ölçümleri bir kez toplanır (CSV), model değeri
*çevre katsayıları olmadan* hesaplanır (yerleşim kıyısı primi dahil, o ölçüldü),
sonra her etken kendi kovalarında ilan/model oranının ortancasıyla kurulur. Etkenler
birbiriyle ilişkili olduğu için sırayla, diğerlerinin o anki katsayısı bölünerek
kurulur (backfitting) ve her tur sonunda tipik kayıt ×1,00 olacak şekilde
normalize edilir: bu katsayılar bölgenin seviyesini değil, bölge içindeki farkı
taşır; seviye ilçe katsayısı ve pazarlık payıyla zaten kalibre edilmiştir.

Sonuç (25 Kasım 2026, 103 ilan): dördü de reddedildi, app/surroundings.py'den
kaldırıldılar. Katsayısız tipik sapma ×1,80 ve 1,5 kat içinde 53 kayıt; eski
katsayılarla aynı ×1,80 ama 1,5 kat 47'ye düşüyor, veriden yeniden kurulduklarında
bile 49'da kalıyor. En umutlu aday ana yol primi de üç sınavı geçemedi (--aday).

    python -P tools/cevre_olc.py --topla    # Overpass + yükselti, CSV yazar (~20 dk)
    python -P tools/cevre_olc.py            # CSV'den katsayıları kurar ve sınar
    python -P tools/cevre_olc.py --loo      # dışarıda bırakmalı sınav
    python -P tools/cevre_olc.py --aday     # tek yanlı adaylar, nötr tabana karşı
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

import ilan_karsilastir as karsilastir  # noqa: E402
from app import market, nearby, urbanity  # noqa: E402
from app.model_params import DEFAULTS  # noqa: E402
from app.surroundings import settlement_position  # noqa: E402
from app.valuation import estimate, load_parameters  # noqa: E402
from olcum_ortak import hedef_tl, yarim_kat_icinde  # noqa: E402

CIKTI = ROOT_DIR / "data" / "private" / "ciktilar" / "cevre_olcum.csv"
IMARLI = {"konut", "ticari", "sanayi"}
ETKENLER = ("coast", "main_road", "services", "slope")
YOK = ""   # ölçüm alınamadı / yarıçap içinde bulunamadı


def _sayi(metin: str) -> float | None:
    return None if metin in ("", "None") else float(metin)


# --- kovalar: bugünkü katsayıların kırılma noktalarıyla aynı, böylece ölçüm
# --- doğrudan o varsayımlara cevap verir -------------------------------------

def kova_coast(m: float | None) -> str:
    if m is None:
        return "3 km icinde kiyi yok"
    return "0-500 m" if m <= 500 else "500-1500 m" if m <= 1500 else "1500-3000 m"


def kova_main_road(m: float | None) -> str:
    if m is None:
        return "1,5 km icinde yol yok"
    return "0-150 m" if m <= 150 else "150-800 m" if m <= 800 else "800-1500 m"


def kova_services(n: int) -> str:
    return "0 nokta" if n == 0 else "1-3" if n <= 3 else "4-11" if n <= 11 else "12+"


def kova_slope(p: float | None) -> str:
    if p is None:
        return "egim olculemedi"
    return "%0-5" if p <= 5 else "%5-10" if p <= 10 else "%10-20" if p <= 20 else "%20+"


def kovalari(s: dict) -> dict[str, str]:
    return {
        "coast": kova_coast(s["coast_m"]),
        "main_road": kova_main_road(s["main_road_m"]),
        "services": kova_services(s["services"]),
        "slope": kova_slope(s["slope_pct"]),
    }


# --- Reddedilen dört katsayı. Bu ölçümden önce app/surroundings.py'de
# --- uygulanıyorlardı; ölçüm modeli bozduklarını gösterdi ve kaldırıldılar.
# --- Burada duruyorlar ki veri büyüdüğünde "eski" sütunu yeniden kıyaslanabilsin.

def eski_coast(m: float | None) -> float:
    """Kıyıda 1,20; 500 m'de ~1,10; 3 km'de etkisiz."""
    return 1.0 if m is None else 1 + 0.20 * math.exp(-m / 700)


def eski_main_road(m: float | None) -> float:
    """150 m içinde 1,05; 800 m'ye kadar nötr; ötesinde 0,95; 1,5 km'de yol yoksa 0,90."""
    if m is None:
        return 0.90
    return 1.05 if m <= 150 else 1.0 if m <= 800 else 0.95


def eski_services(n: int) -> float:
    """Hiç hizmet noktası yoksa 0,95; 12 ve üzerinde 1,05."""
    return 0.95 + 0.10 * min(n, 12) / 12


def eski_slope(p: float) -> float:
    """%5'e kadar düz sayılır; %25 ve üzeri eğimde 0,85."""
    return 1.0 - 0.15 * min(max(p - 5, 0.0), 20.0) / 20


def eski_katsayilar(s: dict) -> dict[str, float]:
    """Ölçümden önce üretimde uygulanan katsayılar."""
    return {
        "coast": eski_coast(s["coast_m"]),
        "main_road": eski_main_road(s["main_road_m"]),
        "services": eski_services(s["services"]),
        "slope": 1.0 if s["slope_pct"] is None else eski_slope(s["slope_pct"]),
    }


# --- katsayı kurma -----------------------------------------------------------

def _carpim(kat: dict[str, dict[str, float]], s: dict, haric: str = "") -> float:
    carpim = 1.0
    for etken in ETKENLER:
        if etken != haric:
            carpim *= kat[etken].get(s["kova"][etken], 1.0)
    return carpim


def kur(satirlar: list[dict], tur_sayisi: int = 4) -> dict[str, dict[str, float]]:
    """Her etkeni kendi kovalarında ortanca oranla kurar; diğerleri bölünür."""
    kat: dict[str, dict[str, float]] = {
        etken: {s["kova"][etken]: 1.0 for s in satirlar} for etken in ETKENLER}
    # Dörtten az kayıtlı kova hiç kurulmaz ve normalizasyona da girmez.
    notr = {etken: {ad for ad in kat[etken]
                    if sum(1 for s in satirlar if s["kova"][etken] == ad) < 4}
            for etken in ETKENLER}
    for _ in range(tur_sayisi):
        for etken in ETKENLER:
            for ad in list(kat[etken]):
                if ad in notr[etken]:
                    kat[etken][ad] = 1.0
                    continue
                grup = [s for s in satirlar if s["kova"][etken] == ad]
                kat[etken][ad] = statistics.median(
                    s["oran"] / _carpim(kat, s, haric=etken) for s in grup)
        # Seviyeyi bozmamak için: tipik kayıt ×1,00 alsın. Az kayıtlı kovalar
        # bu bölmenin dışında tutulur -- Codex'in DX-17'de yakaladığı hata buydu:
        # kova 1,00'e sabitlenip hemen ardından ortancaya bölününce nötr kalmıyor,
        # ortancası 1,25 olan bir etkende sessizce 0,80'e dönüyordu.
        for etken in ETKENLER:
            orta = statistics.median(kat[etken][s["kova"][etken]] for s in satirlar)
            for ad in kat[etken]:
                if ad not in notr[etken]:
                    kat[etken][ad] /= orta
    return kat


def puan(satirlar: list[dict], kat_fn) -> tuple[float, int, int, list[float]]:
    sapmalar = []
    for s in satirlar:
        oran = s["oran"] / kat_fn(s)
        sapmalar.append(abs(math.log2(oran)))
    tipik = 2 ** statistics.mean(sapmalar)
    icinde = sum(1 for s in satirlar
                 if yarim_kat_icinde(s["oran"] / kat_fn(s)))
    return tipik, icinde, len(satirlar), sapmalar


def _eski_carpim(s: dict) -> float:
    return math.prod(eski_katsayilar(s).values())


def rapor(satirlar: list[dict], kat: dict[str, dict[str, float]]) -> None:
    print("\n== ETKENLERIN KENDI SINYALI (oran = ilan / cevre katsayisiz model) ==")
    for etken in ETKENLER:
        print(f"\n  {etken}")
        for ad in sorted(kat[etken]):
            grup = [s for s in satirlar if s["kova"][etken] == ad]
            if not grup:
                continue
            oranlar = [s["oran"] / _carpim(kat, s, haric=etken) for s in grup]
            simdi = statistics.median(eski_katsayilar(s)[etken] for s in grup)
            print(f"    {ad:24} n={len(grup):3}  ortanca artik oran={statistics.median(oranlar):5.2f}"
                  f"   olculen={kat[etken][ad]:5.2f}  eski={simdi:5.2f}")

    print("\n== SINAV ==")
    for ad, fn in (("cevre katsayisi yok   ", lambda s: 1.0),
                   ("eski katsayilar       ", _eski_carpim),
                   ("olculen katsayilar    ", lambda s: _carpim(kat, s))):
        tipik, icinde, n, _ = puan(satirlar, fn)
        print(f"  {ad} tipik sapma=x{tipik:4.2f}  1,5 kat icinde={icinde:3}/{n}")

    _, _, _, bugun = puan(satirlar, _eski_carpim)
    _, _, _, olcum = puan(satirlar, lambda s: _carpim(kat, s))
    iyi = sum(1 for a, b in zip(bugun, olcum) if b < a - 1e-9)
    kotu = sum(1 for a, b in zip(bugun, olcum) if b > a + 1e-9)
    print(f"  eski -> olculen: {iyi} kayit iyilesiyor, {kotu} kayit bozuluyor")

    _, _, _, yoksuz = puan(satirlar, lambda s: 1.0)
    iyi = sum(1 for a, b in zip(yoksuz, olcum) if b < a - 1e-9)
    kotu = sum(1 for a, b in zip(yoksuz, olcum) if b > a + 1e-9)
    print(f"  katsayisiz -> olculen: {iyi} kayit iyilesiyor, {kotu} kayit bozuluyor")

    # Dordu birlikte sinavi gecmezse, iceride bir tanesi geciyor olabilir:
    # her etken tek basina, otekiler notrken olculur.
    print("\n== ETKENLER TEK BASINA (otekiler notr) ==")
    for etken in ETKENLER:
        for ad, fn in ((f"{etken} eski", lambda s, e=etken: eski_katsayilar(s)[e]),
                       (f"{etken} olculen", lambda s, e=etken: kat[e].get(s["kova"][e], 1.0))):
            tipik, icinde, n, sapma = puan(satirlar, fn)
            iyi = sum(1 for a, b in zip(yoksuz, sapma) if b < a - 1e-9)
            kotu = sum(1 for a, b in zip(yoksuz, sapma) if b > a + 1e-9)
            print(f"  {ad:22} tipik sapma=x{tipik:4.2f}  1,5 kat icinde={icinde:3}/{n}"
                  f"   {iyi} iyi / {kotu} bozuk")
    tipik, icinde, n, _ = puan(satirlar, lambda s: 1.0)
    print(f"  {'(katsayisiz taban)':22} tipik sapma=x{tipik:4.2f}  1,5 kat icinde={icinde:3}/{n}")

    print("\n== IMARLI / IMARSIZ AYRIMI ==")
    for ad, sart in (("imarli ", lambda s: s["imarsiz"] == "0"),
                     ("imarsiz", lambda s: s["imarsiz"] == "1")):
        grup = [s for s in satirlar if sart(s)]
        if not grup:
            continue
        for etiket, fn in (("katsayisiz", lambda s: 1.0), ("eski      ", _eski_carpim),
                           ("olculen   ", lambda s: _carpim(kat, s))):
            tipik, icinde, n, _ = puan(grup, fn)
            print(f"  {ad} {etiket} tipik sapma=x{tipik:4.2f}  1,5 kat icinde={icinde:3}/{n}")


def _yol_primi(esik_m: float, prim: float, ceza: float = 1.0):
    def fn(s: dict) -> float:
        m = s["main_road_m"]
        if m is None:
            return ceza
        return prim if m <= esik_m else 1.0
    return fn


def adaylar(satirlar: list[dict]) -> None:
    """Tek yanlı adaylar: yalnız prim veren, eksik veriyi cezalandırmayan biçimler.

    Dörtlü birlikte çöktükten sonra sorulan soru şu: kovalarda görünen en güçlü
    desen -- 150 m içinde ana yol olan parselde artık oran 1,52 -- tek başına,
    ceza olmadan uygulanırsa tutuyor mu? Tutmuyor; aşağıdaki üç blok bunu gösterir.
    """
    def skor(ad: str, fn, grup: list[dict] | None = None) -> None:
        grup = grup if grup is not None else satirlar
        taban = [abs(math.log2(s["oran"])) for s in grup]
        yeni = [abs(math.log2(s["oran"] / fn(s))) for s in grup]
        icinde = sum(1 for s in grup if yarim_kat_icinde(s["oran"] / fn(s)))
        iyi = sum(1 for a, b in zip(taban, yeni) if b < a - 1e-9)
        kotu = sum(1 for a, b in zip(taban, yeni) if b > a + 1e-9)
        print(f"  {ad:30} x{2 ** statistics.mean(yeni):4.2f}  1,5 kat icinde={icinde:3}/{len(grup)}"
              f"  {iyi:3} iyi / {kotu:3} bozuk")

    print("\n== TEK YANLI ADAYLAR (notr tabana karsi) ==")
    skor("notr taban", lambda s: 1.0)
    for prim in (1.15, 1.21, 1.25, 1.36):
        skor(f"yol<=150 m primi x{prim:4.2f}", _yol_primi(150, prim))
    for esik in (250, 400):
        skor(f"yol<={esik} m primi x1.25", _yol_primi(esik, 1.25))
    skor("hizmet 4+ cezasi x0.80", lambda s: 0.80 if s["services"] >= 4 else 1.0)
    skor("kiyi 1,5-3 km x0.75",
         lambda s: 0.75 if s["coast_m"] is not None and s["coast_m"] > 1500 else 1.0)

    print("\n== AYKIRI BES KAYIT CIKARILDI ==")
    kalan = sorted(satirlar, key=lambda s: abs(math.log2(s["oran"])), reverse=True)[5:]
    skor("notr taban", lambda s: 1.0, kalan)
    for prim in (1.15, 1.21, 1.36):
        skor(f"yol<=150 m primi x{prim:4.2f}", _yol_primi(150, prim), kalan)

    print("\n== DISARIDA BIRAKMALI (prim kalan kayitlardan kurulur) ==")
    notr, primli, primler = [], [], []
    yakin = lambda s: s["main_road_m"] is not None and s["main_road_m"] <= 150  # noqa: E731
    for i, s in enumerate(satirlar):
        baskalari = satirlar[:i] + satirlar[i + 1:]
        prim = (statistics.median(k["oran"] for k in baskalari if yakin(k))
                / statistics.median(k["oran"] for k in baskalari if not yakin(k)))
        primler.append(prim)
        notr.append(s["oran"])
        primli.append(s["oran"] / (prim if yakin(s) else 1.0))
    for ad, o in (("notr", notr), ("LOO yol primi", primli)):
        print(f"  {ad:16} x{2 ** statistics.mean(abs(math.log2(x)) for x in o):4.2f}"
              f"  1,5 kat icinde={sum(1 for x in o if yarim_kat_icinde(x)):3}/{len(o)}")
    iyi = sum(1 for a, b in zip(notr, primli) if abs(math.log2(b)) < abs(math.log2(a)) - 1e-9)
    kotu = sum(1 for a, b in zip(notr, primli) if abs(math.log2(b)) > abs(math.log2(a)) + 1e-9)
    print(f"  {iyi} kayit iyilesiyor, {kotu} kayit bozuluyor;  "
          f"kurulan prim {min(primler):.2f}-{max(primler):.2f}, ortanca {statistics.median(primler):.2f}")


def loo(satirlar: list[dict]) -> None:
    """Her kayit, kendisi haric kalanlardan kurulan katsayiyla puanlanir."""
    print("\n== DISARIDA BIRAKMALI ==")
    sonuc = {"yok": [], "bugun": [], "olcum": []}
    for i, s in enumerate(satirlar):
        kat = kur(satirlar[:i] + satirlar[i + 1:])
        sonuc["yok"].append(s["oran"])
        sonuc["bugun"].append(s["oran"] / _eski_carpim(s))
        sonuc["olcum"].append(s["oran"] / _carpim(kat, s))
    for ad, oranlar in sonuc.items():
        tipik = 2 ** statistics.mean(abs(math.log2(o)) for o in oranlar)
        icinde = sum(1 for o in oranlar if yarim_kat_icinde(o))
        print(f"  {ad:8} tipik sapma=x{tipik:4.2f}  1,5 kat icinde={icinde:3}/{len(oranlar)}")


# --- veri toplama ------------------------------------------------------------

def _anahtar(lat, lng) -> str:
    return f"{float(lat):.5f},{float(lng):.5f}"


async def topla(bekle_s: float = 1.0) -> None:
    """Olcumleri toplar. CSV varsa yalnizca eksik kayitlari ekler: Overpass gun
    icinde 30 kaydi uste uste reddedebiliyor, o blok ikinci turda tamamlanir."""
    kayitlar = [k for k in karsilastir.oku() if not k["haric"]]
    indirim = load_parameters().asking_discount
    satirlar: list[dict] = []
    if CIKTI.exists():
        satirlar = list(csv.DictReader(CIKTI.open(encoding="utf-8")))
        var = {_anahtar(s["lat"], s["lng"]) for s in satirlar}
        kayitlar = [k for k in kayitlar if _anahtar(k["lat"], k["lng"]) not in var]
        print(f"CSV'de {len(satirlar)} kayit var; {len(kayitlar)} eksik toplanacak",
              flush=True)
    print(f"{len(kayitlar)} kayit - Overpass + yukselti (yaklasik "
          f"{len(kayitlar) * (10 + bekle_s) / 60:.0f} dk)\n", flush=True)
    for sira, k in enumerate(kayitlar, 1):
        try:
            yer = urbanity.describe(k["lat"], k["lng"])
            if yer is None:
                continue
            housing = await market.housing_price(k["il"])
            # Cevre katsayilari olmadan, ama olculmus yerlesim kiyisi primi dahil:
            # prim bu dortluye yeniden yuklenmesin.
            e = estimate(area_m2=k["alan"], usage=k["usage"], housing=housing, urban=yer,
                         surroundings=None, kaks=k["kaks"], **k["cevaplar"])
            cevre = await nearby.fetch(k["lat"], k["lng"])
            if cevre.osm is None:
                print(f"  {sira}/{len(kayitlar)} {k['etiket']}: OSM yok", flush=True)
                continue
            prim = (DEFAULTS.fringe_premium
                    if k["usage"] not in IMARLI
                    and settlement_position(cevre.osm) == "kiyi" else 1.0)
        except Exception as hata:                              # noqa: BLE001
            print(f"  {sira}/{len(kayitlar)} {k['etiket']}: {type(hata).__name__}: {hata}",
                  flush=True)
            continue
        hedef = hedef_tl(k["deger"], k["tur"], indirim)
        if hedef is None:
            print(f"  {sira}/{len(kayitlar)} {k['etiket']}: bilinmeyen deger_turu, olcum disi",
                  flush=True)
            continue
        hedef /= k["alan"]
        satirlar.append(dict(
            il=k["il"], ilce=k["ilce"], konum=k["konum"], imar=k["usage"],
            imarsiz="0" if k["usage"] in IMARLI else "1",
            model_tl_m2=e.unit_price, fringe=prim,
            oran=round(hedef / (e.unit_price * prim), 4),
            coast_m="" if cevre.osm.coast_m is None else round(cevre.osm.coast_m),
            main_road_m="" if cevre.osm.main_road_m is None else round(cevre.osm.main_road_m),
            services=cevre.osm.services,
            slope_pct="" if cevre.slope_pct is None else round(cevre.slope_pct, 1),
            buildings=cevre.osm.buildings,
            built_up_m="" if cevre.osm.built_up_m is None else round(cevre.osm.built_up_m),
            lat=k["lat"], lng=k["lng"]))
        print(f"  {sira}/{len(kayitlar)} {k['etiket']:22} kiyi={satirlar[-1]['coast_m'] or '-':>5} "
              f"yol={satirlar[-1]['main_road_m'] or '-':>5} hizmet={cevre.osm.services:3} "
              f"egim={satirlar[-1]['slope_pct'] or '-':>5} oran={satirlar[-1]['oran']:5.2f}",
              flush=True)
        await asyncio.sleep(bekle_s)

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    with CIKTI.open("w", encoding="utf-8", newline="") as dosya:
        yazici = csv.DictWriter(dosya, fieldnames=list(satirlar[0]))
        yazici.writeheader()
        yazici.writerows(satirlar)
    print(f"\nCSV: {CIKTI}  ({len(satirlar)} kayit)")


def oku_csv() -> list[dict]:
    satirlar = []
    for s in csv.DictReader(CIKTI.open(encoding="utf-8")):
        s["oran"] = float(s["oran"])
        s["services"] = int(s["services"])
        s["buildings"] = int(s["buildings"])
        for alan in ("coast_m", "main_road_m", "slope_pct", "built_up_m"):
            s[alan] = _sayi(s[alan])
        s["kova"] = kovalari(s)
        satirlar.append(s)
    return satirlar


def main() -> None:
    if "--topla" in sys.argv:
        asyncio.run(topla(bekle_s=3.0 if "--yavas" in sys.argv else 1.0))
        return
    satirlar = oku_csv()
    print(f"{len(satirlar)} kayit okundu  (imarsiz={sum(1 for s in satirlar if s['imarsiz'] == '1')})")
    kat = kur(satirlar)
    rapor(satirlar, kat)
    if "--aday" in sys.argv:
        adaylar(satirlar)
    if "--loo" in sys.argv:
        loo(satirlar)


if __name__ == "__main__":
    main()
