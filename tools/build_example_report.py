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
  <link rel="stylesheet" href="style.css">
  <link rel="stylesheet" href="ornek-rapor.css">
</head>
<body>
  <a class="atla" href="#icerik">İçeriğe atla</a>
  <header class="site-header">
    <a class="site-brand" href="./">Değerix</a>
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
      <a href="{escape(url)}">Güncel sorgu için parseli haritada aç</a>
    </footer>
  </main>
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
