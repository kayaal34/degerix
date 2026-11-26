"""Ada/parsel listesini toplu değerler: ÇKS belgesi, tapu dökümü ya da elle liste.

Girdi, her satırı bir parsel olan bir metin dosyasıdır. Sütunlar `;` ile ayrılır:

    il;ilce;mahalle;ada;parsel[;imar][;emsal]

`imar` verilmezse TKGM niteliğinden tahmin edilir (tarla, bağ/bahçe, konut...),
`emsal` verilmezse yerleşim sınıfının varsayılanı kullanılır. Alan TKGM tapu
kaydından gelir; ÇKS'deki dekar değeri kullanılmaz, çünkü tapu alanı esastır.

    python tools/toplu_degerle.py liste.txt
    python tools/toplu_degerle.py liste.txt --csv sonuc.csv

Her satır için bulunan parselin ada/parsel numarası ve alanı yazdırılır; bulunamayan
satır sessizce atlanmaz, sebebiyle birlikte listelenir. Hiçbir sonuç kesinlik vaadi
değildir: ekranda ayrıca modelin ölçülmüş hata payı (değer aralığı) gösterilir.
"""

import argparse
import asyncio
import csv
import sys
import unicodedata
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT_DIR / ".env")

from app import evds, market, nearby, nominatim, tkgm, urbanity  # noqa: E402
from app.errors import NotFound, UpstreamError  # noqa: E402
from app.geo import _outer_rings  # noqa: E402
from app.valuation import estimate, guess_usage  # noqa: E402

# Çevre sorgusu (OSM + eğim) parsel başına birkaç saniye sürebiliyor; toplu işte
# uygulamadakinden geniş bir bütçe veriyoruz ama yine de sınırlı tutuyoruz.
CEVRE_BUTCE_S = 8.0


def sadelestir(metin: str) -> str:
    """Türkçe karakter ve büyük/küçük farkını yok sayan karşılaştırma anahtarı."""
    metin = (metin or "").strip().lower()
    metin = metin.replace("ı", "i").replace("İ", "i")
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(h for h in metin if not unicodedata.combining(h))
    for ek in (" mahallesi", " mah.", " mah", " koyu", " köyü", " merkez"):
        if metin.endswith(ek):
            metin = metin[: -len(ek)]
    return metin.strip()


def _bul(yerler: list[dict], ad: str) -> dict | None:
    hedef = sadelestir(ad)
    for yer in yerler:
        if sadelestir(yer.get("name", "")) == hedef:
            return yer
    # Tam eşleşme yoksa içerme: "Çanta Balaban" ile "Balaban" aynı mahalle olabiliyor.
    adaylar = [y for y in yerler if hedef and hedef in sadelestir(y.get("name", ""))]
    return adaylar[0] if len(adaylar) == 1 else None


async def mahalle_id(il: str, ilce: str, mahalle: str) -> int:
    iller = await tkgm.list_provinces()
    il_kaydi = _bul(iller, il)
    if il_kaydi is None:
        raise NotFound(f"il bulunamadı: {il}")
    ilceler = await tkgm.list_districts(int(il_kaydi["id"]))
    ilce_kaydi = _bul(ilceler, ilce)
    if ilce_kaydi is None:
        raise NotFound(f"ilçe bulunamadı: {ilce}")
    mahalleler = await tkgm.list_neighborhoods(int(ilce_kaydi["id"]))
    mahalle_kaydi = _bul(mahalleler, mahalle)
    if mahalle_kaydi is None:
        raise NotFound(f"mahalle/köy bulunamadı: {mahalle}")
    return int(mahalle_kaydi["id"])


class BelirsizSayi(ValueError):
    """Metin hem binlik hem ondalık okunabiliyor; tahmin etmek yerine durur."""


def alan_oku(metin: str) -> float:
    """Alan metnini sayıya çevirir. Belirsizse tahmin etmez, hata verir.

    Bu alan m² cinsinden ve değerin tamamı m² üzerinden kuruluyor; yanlış
    okunan bir ayraç tutarı on ya da bin kat kaydırır ve kimse fark etmez.
    O yüzden kurallar dar, belirsiz hâl ise açıkça reddediliyor:

      "1.234,5"   -> 1234.5    iki ayraç birden: nokta binlik, virgül ondalık
      "55,5"      -> 55.5      yalnız virgül: Türkçe ondalık
      "1.000.000" -> 1000000   birden çok nokta: binlik ayracı
      "55.5"      -> 55.5      tek nokta, ardından 3 hane değil: ondalık
      "1234"      -> 1234      ayraçsız
      "10.000"    -> HATA      tek nokta + tam 3 hane: 10 m² mi 10.000 m² mi?

    Son satır bilerek hata. "10.000" yazan biri neredeyse kesin on bin m²
    demek istiyor, ama "1.234" yazan biri bin iki yüz otuz dört de diyor
    olabilir 1,234 de. İkisini ayırmanın güvenilir yolu yok; sessizce
    tahmin etmektense kullanıcıdan "10000" ya da "10.000,0" yazmasını
    istemek doğru. Depodaki kayıtların hepsi ayraçsız tam sayı, yani bu
    kural var olan veriyi etkilemiyor — gelecekteki bir yazımı yakalıyor.
    """
    metin = metin.strip()
    if "," in metin:
        return float(metin.replace(".", "").replace(",", "."))
    if metin.count(".") > 1:
        return float(metin.replace(".", ""))
    if metin.count(".") == 1:
        _, _, kesir = metin.partition(".")
        if len(kesir) == 3 and kesir.isdigit():
            raise BelirsizSayi(
                f"{metin!r} hem {metin.replace('.', '')} hem {metin} okunabilir; "
                f"binlik ayracı için {metin.replace('.', '')}, ondalık için {metin},0 yazın"
            )
    return float(metin)


def satirlari_oku(yol: Path) -> list[dict[str, str]]:
    satirlar = []
    for ham in yol.read_text(encoding="utf-8").splitlines():
        ham = ham.strip()
        if not ham or ham.startswith("#"):
            continue
        parca = [p.strip() for p in ham.split(";")]
        if len(parca) < 5:
            print(f"  ATLANDI (5 sütun gerekli): {ham}")
            continue
        satirlar.append({
            "il": parca[0], "ilce": parca[1], "mahalle": parca[2],
            "ada": parca[3], "parsel": parca[4],
            "imar": parca[5] if len(parca) > 5 and parca[5] else "",
            "emsal": parca[6] if len(parca) > 6 and parca[6] else "",
            # ÇKS belgesi her parsel için sulu/kuru yazar; model bunu imarsız
            # arazide doğrudan kullanıyor (sulu ×1,20, kuru ×0,90).
            "sulama": parca[7] if len(parca) > 7 and parca[7] else "",
            "not": parca[8] if len(parca) > 8 and parca[8] else "",
            # TKGM kaydı bulunamazsa kullanılacak yedek alan (ör. ÇKS tapu alanı).
            "alan_m2": parca[9] if len(parca) > 9 and parca[9] else "",
        })
    return satirlar


async def koy_merkezi(giris: dict[str, str]) -> tuple[float, float]:
    """TKGM parseli veremediğinde köyün merkezi (Nominatim).

    Konum parselin kendisi değil köy çekirdeği olur; ölçümde bunun farkı büyük
    (mahalle merkezli kayıtlarda ortanca oran 0,84, parsel pinli kayıtlarda 1,02),
    o yüzden sonuç tabloda ayrıca işaretlenir.
    """
    for sorgu in (f"{giris['mahalle']}, {giris['ilce']}, {giris['il']}",
                  f"{giris['mahalle']} köyü, {giris['ilce']}, {giris['il']}"):
        bulunan = await nominatim.search(sorgu, limit=1)
        if bulunan:
            return float(bulunan[0]["lat"]), float(bulunan[0]["lng"])
    raise NotFound(f"köyün konumu bulunamadı: {giris['mahalle']}")


async def degerle(giris: dict[str, str]) -> dict:
    """Tek parsel: TKGM kaydı + yerleşim sınıfı + çevre ile değerleme."""
    hucre = await mahalle_id(giris["il"], giris["ilce"], giris["mahalle"])
    ozellik: dict = {}
    kaynak = "TKGM parseli"
    try:
        parsel = await tkgm.parcel_by_number(hucre, giris["ada"], giris["parsel"])
        ozellik = parsel["properties"]
        alan = tkgm.parse_area(ozellik.get("alan"))
        # Parselin merkezi: poligonun köşe ortalaması. Yerleşim sınıfı ve çevre bundan
        # okunur, yani ÇKS'deki köy adından değil parselin kendi yerinden.
        # Polygon da MultiPolygon da app.geo'nun dış halka ayrıştırıcısından geçer.
        noktalar = [nokta for halka in _outer_rings(parsel["geometry"]) for nokta in halka]
        if not noktalar:
            raise ValueError("parsel geometrisi boş")
        lng = sum(nokta[0] for nokta in noktalar) / len(noktalar)
        lat = sum(nokta[1] for nokta in noktalar) / len(noktalar)
    except NotFound:
        # TKGM her köyün kadastrosunu yayımlamıyor: Bandırma'nın 55 mahallesinden
        # bazılarının ne parseli ne sınırı dönüyor. Elde ÇKS'nin tapu alanı varsa
        # değerleme köy merkezi koordinatıyla yine de yapılır, ama işaretlenir.
        if not giris.get("alan_m2"):
            raise
        alan = alan_oku(giris["alan_m2"])
        lat, lng = await koy_merkezi(giris)
        kaynak = "ÇKS alanı · köy merkezi"
    if not alan:
        raise NotFound("tapu alanı okunamadı")

    imar = giris["imar"] or guess_usage(ozellik.get("nitelik"))
    housing = await market.housing_price(giris["il"])
    yer = urbanity.describe(lat, lng)
    try:
        cevre = await nearby.fetch_within(lat, lng, budget_s=CEVRE_BUTCE_S)
    except (UpstreamError, OSError):
        cevre = None

    sonuc = estimate(
        area_m2=alan, usage=imar, housing=housing, urban=yer, surroundings=cevre,
        kaks=alan_oku(giris["emsal"]) if giris["emsal"] else None,
        irrigation=giris.get("sulama") or "bilinmiyor",
    )
    return {
        "il": giris["il"], "ilce": giris["ilce"], "mahalle": giris["mahalle"],
        "ada": ozellik.get("adaNo") or giris["ada"],
        "parsel": ozellik.get("parselNo") or giris["parsel"],
        "nitelik": ozellik.get("nitelik") or "",
        "alan_m2": round(alan),
        "imar": imar,
        "yerlesim": sonuc.settlement,
        "yontem": sonuc.basis,
        "birim_tl_m2": sonuc.unit_price,
        "deger_tl": sonuc.total,
        "alt_tl": sonuc.low,
        "ust_tl": sonuc.high,
        "guven": sonuc.confidence,
        "kaynak": kaynak,
        "sulama": giris.get("sulama") or "",
        "not": giris.get("not") or "",
        "lat": round(lat, 6), "lng": round(lng, 6),
    }


async def main() -> None:
    ayristirici = argparse.ArgumentParser(description="Ada/parsel listesini toplu değerler")
    ayristirici.add_argument("liste", type=Path, help="il;ilce;mahalle;ada;parsel satırları")
    ayristirici.add_argument("--csv", type=Path, help="sonuçları bu dosyaya da yaz")
    secenek = ayristirici.parse_args()

    girisler = satirlari_oku(secenek.liste)
    if not girisler:
        sys.exit("Listede işlenecek satır yok.")
    print(f"{len(girisler)} parsel okunacak...\n")

    sonuclar, hatalar = [], []
    nedenler: dict[str, int] = {}
    try:
        for sira, giris in enumerate(girisler, 1):
            etiket = f"{giris['il']}/{giris['ilce']}/{giris['mahalle']} {giris['ada']}/{giris['parsel']}"
            try:
                sonuclar.append(await degerle(giris))
            except Exception as hata:  # noqa: BLE001 — tek bozuk satır koşunun tamamını düşürmesin
                neden = type(hata).__name__
                nedenler[neden] = nedenler.get(neden, 0) + 1
                hatalar.append(f"{etiket}: {neden}: {hata}")
            print(f"  {sira}/{len(girisler)} {etiket}", flush=True)

        print(f"\n{'ada/parsel':>14} {'mahalle':16} {'alan m²':>9} {'imar':10} "
              f"{'₺/m²':>9} {'değer':>14} {'aralık':>26} {'yöntem':10} {'güven':8} {'kaynak':22} not")
        toplam = 0
        for s in sonuclar:
            toplam += s["deger_tl"]
            print(f"{s['ada'] + '/' + s['parsel']:>14} {s['mahalle'][:16]:16} {s['alan_m2']:>9,} "
                  f"{s['imar']:10} {s['birim_tl_m2']:>9,} {s['deger_tl']:>14,} "
                  f"{s['alt_tl']:>11,} – {s['ust_tl']:>11,} {s['yontem']:10} {s['guven']:8} {s['kaynak']:22} {s['not']}")
        if sonuclar:
            print(f"\nTOPLAM: {toplam:,} ₺ · {len(sonuclar)} parsel")
            print("Değerler modeldir, ekspertiz değildir; aralık modelin ölçülmüş hatasından gelir.")

        if hatalar:
            print(f"\n== BULUNAMAYAN ({len(hatalar)}) ==")
            for satir in hatalar:
                print("  " + satir)
            print("  Özet: " + ", ".join(f"{n} satır {k}" for k, n in sorted(nedenler.items())))

        if secenek.csv and sonuclar:
            with secenek.csv.open("w", encoding="utf-8", newline="") as dosya:
                yazici = csv.DictWriter(dosya, fieldnames=list(sonuclar[0]))
                yazici.writeheader()
                yazici.writerows(sonuclar)
            print(f"\nCSV yazıldı: {secenek.csv}")
    finally:
        await tkgm.close()
        await nominatim.close()
        await evds.close()


if __name__ == "__main__":
    asyncio.run(main())
