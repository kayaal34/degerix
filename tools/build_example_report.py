"""Generate the public parcel valuation example from the repository data.

Run from the repository root:
    python -m tools.build_example_report --date YYYY-MM-DD --revision COMMIT
"""
import argparse
from datetime import date
from html import escape
from pathlib import Path
import re
from urllib.parse import urlencode

from app import market, urbanity
from app.valuation import estimate

OUTPUT = Path(__file__).resolve().parents[1] / "static" / "ornek-rapor.html"


def number(value: int | float) -> str:
    result = f"{value:,.2f}".rstrip("0").rstrip(".")
    return result.translate(str.maketrans(",.", ".,"))


def render(generated: date, revision: str) -> str:
    lat, lng = 40.369137, 28.89647
    area = 4683.02
    housing = market.snapshot_price("Bursa")
    assert housing is not None
    result = estimate(
        area_m2=area, usage="konut", housing=housing, urban=urbanity.describe(lat, lng),
        kaks=1.2, deed="tam", road="var", utilities="var", view="yok",
    )
    url = "harita.html?" + urlencode({"lat":lat, "lng":lng, "mahalle":39428, "ada":1503, "parsel":17})
    scenarios = "".join(
        f"<li><strong>{escape(item.label)}</strong><span>{number(item.value)} TL</span></li>"
        for item in result.scenarios
    )
    factors = "".join(
        f"<li><strong>{escape(item.label)}</strong><span>{escape(item.detail)}</span></li>"
        for item in result.factors
    )
    return f"""<!doctype html>
<!-- Üretim: python -m tools.build_example_report --date {generated.isoformat()} --revision {revision} -->
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Değerix örnek arsa raporu. Tapu kaydı, hesap varsayımları, veri dönemi ve fiyat aralığı.">
  <title>Örnek arsa raporu · Değerix</title>
  <meta name="theme-color" content="#14543a">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%2314543a'/%3E%3Cpath d='M8 8h4.2v16H8z' fill='%23fff' fill-opacity='.62'/%3E%3Cpath d='M13.2 8H16.8a7.6 7.6 0 0 1 7.6 7.6H13.2Z' fill='%23fff'/%3E%3Cpath d='M13.2 16.4H24.4A7.6 7.6 0 0 1 16.8 24H13.2Z' fill='%23fff' fill-opacity='.62'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&amp;family=Source+Serif+4:opsz,wght@8..60,500..700&amp;display=swap">
  <link rel="stylesheet" href="style.css">
  <link rel="stylesheet" href="ornek-rapor.css">
</head>
<body>
  <a class="atla" href="#icerik">İçeriğe atla</a>
  <header class="site-header">
    <a class="site-brand" href="./"><svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" focusable="false">
        <rect width="32" height="32" rx="8" fill="currentColor"/>
        <path d="M8 8h4.2v16H8z" fill="#fff" fill-opacity=".62"/>
        <path d="M13.2 8H16.8a7.6 7.6 0 0 1 7.6 7.6H13.2Z" fill="#fff"/>
        <path d="M13.2 16.4H24.4A7.6 7.6 0 0 1 16.8 24H13.2Z" fill="#fff" fill-opacity=".62"/>
      </svg>
      Değerix</a>
    <a class="btn btn-ghost" href="{escape(url)}">Parseli haritada aç</a>
  </header>
  <main class="report-sample" id="icerik" tabindex="-1">
    <header class="sample-title">
      <h1>Örnek arsa raporu</h1>
      <p>Bursa / Mudanya / Ömerbey · 1503 ada, 17 parsel</p>
    </header>
    <section class="sample-summary" aria-labelledby="summary-title">
      <h2 id="summary-title">Tahmini piyasa değeri</h2>
      <strong class="sample-total">{number(result.total)} TL</strong>
      <p>Tahmini aralık <strong>{number(result.low)} – {number(result.high)} TL</strong></p>
      <p>{number(result.unit_price)} TL/m² · {escape(result.settlement)}</p>
    </section>
    <div class="sample-grid">
      <section class="sample-card" aria-labelledby="parcel-source">
        <h2 id="parcel-source">Kayıt ve varsayımlar</h2>
        <dl>
          <dt>TKGM kaydı</dt><dd>Arsa · {number(area)} m²</dd>
          <dt>Örnek hesap girdisi</dt><dd>Konut kullanımı · KAKS 1,20</dd>
          <dt>Örnek beyanlar</dt><dd>Müstakil tapu, yol cephesi, elektrik ve su var. Manzara yok.</dd>
        </dl>
        <p>İmar ve diğer beyanlar örnek hesap için seçildi. Belediyeden doğrulanmış imar bilgisi kullanılmadı.</p>
      </section>
      <section class="sample-card" aria-labelledby="data-source">
        <h2 id="data-source">Veri dönemi ve model</h2>
        <dl>
          <dt>Konut fiyatı</dt><dd>Bursa · {number(housing.value)} TL/m² · {escape(housing.period)}</dd>
          <dt>Fiyat kaynağı</dt><dd>{escape(housing.source)}</dd>
          <dt>Rapor tarihi</dt><dd><time datetime="{generated.isoformat()}">{generated.strftime("%d.%m.%Y")}</time></dd>
          <dt>Model kodu</dt><dd><a href="https://github.com/kayaal34/degerix/tree/{revision}">{revision[:7]}</a></dd>
        </dl>
      </section>
    </div>
    <section class="sample-card">
      <h2>Fiyat senaryoları</h2>
      <ul class="sample-scenarios">{scenarios}</ul>
      <p>Tutarlar model senaryolarıdır. Bu örnek için ilan fiyatı, gerçekleşmiş satış veya ihale bedeli kullanılmadı.</p>
    </section>
    <section class="sample-card">
      <h2>Hesabın dayanakları</h2>
      <p><strong>{escape(result.base_label)}</strong> · {escape(result.base_detail)}</p>
      <ul class="sample-factors">{factors}</ul>
    </section>
    <footer class="sample-note">
      <p>Bu sayfa tarihli bir ön tahmindir. Lisanslı değerleme raporu yerine geçmez ve resmî işlemlerde dayanak olarak kullanılamaz.</p>
      <p>Buradaki rakamlar <b>depodaki fiyat kopyasıyla</b> üretildi; örnek her
        açılışta aynı kalsın diye. Aşağıdaki bağlantıdan aynı parseli haritada
        hesaplarsanız Merkez Bankası’nın o günkü verisi kullanılır ve sonuç
        farklı çıkabilir. Fark hata değil, veri döneminin farkıdır.</p>
      <a href="{escape(url)}">Güncel sorgu için parseli haritada aç</a>
    </footer>
  </main>

  <footer class="site-footer">
    <nav class="footer-baglantilar" aria-label="Hukuki metinler ve yardım">
      <a href="./">Ana sayfa</a>
      <a href="harita.html">Haritayı aç</a>
      <a href="sss.html">Sıkça sorulan sorular</a>
      <a href="abonelik.html">Abonelik</a>
      <a href="kvkk.html">KVKK aydınlatma metni</a>
      <a href="gizlilik.html">Gizlilik</a>
      <a href="kosullar.html">Kullanım koşulları</a>
    </nav>
    <p class="footer-not">Değerix lisanslı değerleme raporu üretmez; çıktısı bilgilendirme
      amaçlıdır, yatırım tavsiyesi ya da resmî işlemlerde dayanak değildir.
      Hukuki metinler taslak hâlindedir.</p>
  </footer>
  <script src="cerez.js"></script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("--revision tam Git commit kimliği olmalı")
    OUTPUT.write_text(render(args.date, args.revision), encoding="utf-8")


if __name__ == "__main__":
    main()
