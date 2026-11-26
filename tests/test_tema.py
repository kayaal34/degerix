"""Tema belirteçlerinin tutarlılığı.

Koyu tema iki ayrı CSS bloğunda tanımlanmak zorunda: biri işletim sistemi
koyu derken (@media prefers-color-scheme), biri kullanıcı elle koyu seçtiğinde
([data-theme="dark"]). Düz CSS'te bu ikisini tek yere yazmanın yolu yok.

İki kopya olan her şey birbirinden ayrı düşer. Buradaki testler bunu
imkânsız kılıyor: biri değişip diğeri kalırsa test kırılır.
"""

import re
from pathlib import Path

import pytest

STYLE = Path(__file__).resolve().parent.parent / "static" / "style.css"


def _bildirimler(govde: str) -> dict[str, str]:
    """CSS gövdesinden --degisken: deger çiftleri."""
    govde = re.sub(r"/\*.*?\*/", "", govde, flags=re.S)
    return {
        ad.strip(): deger.strip()
        for ad, deger in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", govde)
    }


@pytest.fixture(scope="module")
def css() -> str:
    return STYLE.read_text(encoding="utf-8")


def _medya_blogu(css: str) -> dict[str, str]:
    kalip = re.compile(
        r'@media \(prefers-color-scheme: dark\) \{\s*'
        r':root:not\(\[data-theme="light"\]\) \{(.*?)\n  \}\s*\}',
        re.S)
    bulunan = [m for m in kalip.finditer(css) if "--bg" in m.group(1)]
    assert bulunan, "koyu tema medya bloğu bulunamadı"
    return _bildirimler(bulunan[0].group(1))


def _elle_blogu(css: str) -> dict[str, str]:
    kalip = re.compile(r':root\[data-theme="dark"\] \{(.*?)\n\}', re.S)
    bulunan = [m for m in kalip.finditer(css) if "--bg" in m.group(1)]
    assert bulunan, "elle seçilen koyu tema bloğu bulunamadı"
    return _bildirimler(bulunan[0].group(1))


def test_iki_koyu_blok_ayni(css):
    """Elle seçilen koyu tema, işletim sisteminin koyusuyla birebir aynı olmalı."""
    medya, elle = _medya_blogu(css), _elle_blogu(css)
    assert medya == elle, (
        "Koyu temanın iki bloğu ayrı düşmüş. Yalnız birinde olanlar: "
        f"{set(medya) ^ set(elle)}; değeri farklı olanlar: "
        f"{ {k for k in set(medya) & set(elle) if medya[k] != elle[k]} }"
    )


def test_koyu_tema_butun_yuzey_ve_yazi_belirteclerini_eziyor(css):
    """Açık temada tanımlı her yüzey/yazı rengi koyuda da yeniden tanımlanmalı.

    Biri atlanırsa koyu temada açık tema rengi kalır: koyu zeminde açık
    çizgi, ya da beyaz zeminde beyaz yazı. Gözle fark edilmeyen ama
    okunmaz hâle getiren türden bir kaçak.
    """
    kok = _bildirimler(re.search(r":root \{(.*?)\n\}", css, re.S).group(1))
    koyu = _medya_blogu(css)
    zorunlu = {ad for ad in kok if ad.split("-")[1] in {
        "bg", "surface", "ink", "muted", "line", "brand", "accent",
        "warn", "error", "map", "paper", "up", "down", "status",
    }}
    # Rampalar temadan bağımsız, onlar ezilmez
    zorunlu = {ad for ad in zorunlu if not ad.startswith(("--kagit", "--yesil", "--pirinc"))}
    eksik = {ad for ad in zorunlu if ad not in koyu}
    # on-brand-* ve brand-ring koyu blokta da gerekmiyor olabilir; onları ayır
    eksik -= {"--on-brand-line", "--on-brand-soft", "--parcel"}
    assert not eksik, f"koyu temada tanımsız kalan belirteçler: {sorted(eksik)}"


def test_bilesenler_rampa_rengini_dogrudan_kullanmaz(css):
    """Rampa adları yalnızca belirteç bloğunda geçmeli.

    Bir bileşen doğrudan --yesil-600 kullanırsa koyu temada o renk
    değişmez ve yama gibi durur. Anlam katmanı tam da bunun için var.
    """
    govde = css[css.index("/* ---------- Temel ---------- */"):]
    govde = re.sub(r"/\*.*?\*/", "", govde, flags=re.S)
    kacaklar = re.findall(r"var\((--(?:kagit|yesil|pirinc)-\d+)", govde)
    assert not kacaklar, f"bileşenler rampadan doğrudan renk alıyor: {sorted(set(kacaklar))}"
