# Değerix

[![Testler](https://github.com/kayaal34/degerix/actions/workflows/tests.yml/badge.svg)](https://github.com/kayaal34/degerix/actions/workflows/tests.yml)

Haritada bir arsaya tıklayın ya da ada/parsel numarasını girin. Değerix, parseli
**TKGM (Tapu ve Kadastro) kaydından** bulur, sınırını haritada çizer; imar, tapu,
yol ve altyapı sorularıyla birlikte tahmini değerini **acil satış, piyasa değeri ve
tok satıcı** senaryoları ve hesabın adım adım dökümüyle gösterir.

**Teknolojiler:** Python 3.12 · FastAPI · httpx · Leaflet · Vanilla JS · pytest · GitHub Actions

## Özellikler

- **Haritadan seçim:** tıklanan noktadaki gerçek parsel TKGM'den gelir: ada, parsel, yüzölçümü, nitelik ve sınır poligonu.
- **Ada / parsel ile arama:** il → ilçe → mahalle listeleri de TKGM'den gelir.
- **Arsa soruları:** imar durumu ve emsal (KAKS, inşaat alanı canlı hesaplanır), müstakil/hisseli tapu (hisse payının değeri ayrıca gösterilir), yol cephesi, elektrik ve su.
- **Satış süresine göre fiyat:** acil satış (1–2 ay), piyasa değeri (3–6 ay) ve tok satıcı (6 ay+) için ayrı fiyat ve aralık.
- **Şeffaf hesap:** değer aralığı, güven düzeyi ve her çarpanın gerekçesi gösterilir. "Bilmiyorum" denen sorular aralığı genişletir.
- **Telefonda:** arsanın üzerindeyken "Bulunduğum yeri seç" ile parseli GPS'ten bulma, dokunmatik uyumlu arayüz.
- **Yer arama** (OpenStreetMap), **harita / uydu görünümü**, **paylaşılabilir bağlantı** (`?lat=..&lng=..`).
- **Yedek akış:** parsel kaydı olmayan noktalarda il/ilçe OpenStreetMap'ten alınır, alanı kullanıcı girer.

## Nasıl çalışır?

```mermaid
flowchart LR
    UI["Tarayıcı<br/>Leaflet + JS"] -->|/api/parcels/at| API["FastAPI"]
    UI -->|/api/estimate| API
    API -->|parsel, ilçe sınırı| TKGM["TKGM Parsel Sorgu"]
    API -->|adres, yer arama| OSM["OpenStreetMap Nominatim"]
    API --> MODEL["valuation.py<br/>saf fonksiyonlar"]
```

Tarayıcı dış servislere doğrudan gitmez; FastAPI araya girer. Böylece TKGM'nin
tutarsız yanıtları tek yerde düzeltilir (ör. alanın bazen `45,911.00`, bazen
`45.911,00` biçiminde gelmesi, "Gölbaşi" gibi bozuk ad yazımları), idari listeler
önbelleğe alınır ve Nominatim'in saniyede bir istek sınırına uyulur.

## Değerleme modeli

Referans fiyat, konut imarlı, emsali 1,00 olan, yola cepheli ve müstakil tapulu arsa içindir.
Diğer her özellik bu fiyatı bir katsayıyla çarpar:

| Çarpan | Nasıl belirlenir | Aralık |
|---|---|---|
| İlçe | bilinen ilçeler için bölge farkı | 0,77 – 2,30 |
| Konum | ilçenin coğrafi merkezine uzaklık (TKGM ilçe sınırından) | 0,85 – 1,10 |
| İmar durumu | konut / ticari / sanayi imarlı ya da imarsız bağ-bahçe, zeytinlik, tarla | 0,22 – 1,45 |
| Emsal (KAKS) | yalnızca imarlı arsada; inşaat hakkı arttıkça değer artar ama orantısız | 0,50 – 1,80 |
| Büyüklük | büyük parselde m² fiyatı düşer | 0,65 – 1,08 |
| Tapu | hisseli tapuda ortaklık indirimi | 0,80 – 1,00 |
| Yol cephesi | yola cephesi yoksa geçit hakkı gerekir | 0,75 – 1,00 |
| Elektrik ve su | eksikse düşer; tarlada etkisi daha az | 0,85 – 1,00 |

**Değer aralığı ve güven:** her eksik bilgi aralığı genişletir. Tanımsız ilçe, alınamayan
konum, imarsız arazi, girilmemiş emsal ve "Bilmiyorum" denen her soru aralığa eklenir.
Kullanıcı yanıtladıkça aralık daralır, güven "düşük → orta → yüksek" olur.

**Satış senaryoları:** piyasa değeri 3–6 aylık normal satışı temsil eder. Acil satışta
imarlı arsa ×0,85, imarsız arazi ×0,78 (arazi daha yavaş satılır); tok satıcıda
×1,08 / ×1,10 uygulanır.

Model deterministiktir: aynı girdi her zaman aynı sonucu verir.

Örnek: Bodrum, Yeniköy, 1108 ada 6 parsel (467,87 m², konut imarlı, sorular yanıtlanmamış)

| Adım | Çarpan | m² fiyatı |
|---|---|---|
| Muğla referans fiyatı | | ₺8.800 |
| İlçe: Bodrum | × 2,30 | |
| Konum: ilçe merkezine 7,8 km | × 0,98 | |
| İmar durumu: konut imarlı | × 1,00 | |
| Emsal: girilmedi, 1,00 varsayıldı | × 1,00 | |
| Büyüklük: 468 m² | × 1,01 | |
| Tapu, yol cephesi, elektrik-su: yanıtlanmadı | × 1,00 | |
| **Sonuç** | | **₺19.900** → **₺9.310.000** |

| Senaryo | Fiyat | Aralık |
|---|---|---|
| Acil satış (1–2 ay) | 7,9 milyon ₺ | 6,5 – 9,3 milyon ₺ |
| Piyasa değeri (3–6 ay) | 9,3 milyon ₺ | 7,6 – 11 milyon ₺ |
| Tok satıcı (6 ay+) | 10,1 milyon ₺ | 8,3 – 11,9 milyon ₺ |

> **Önemli:** `app/data.py` içindeki referans fiyatlar ve katsayılar gerçek piyasa verisi
> değil, modelin çalışmasını göstermek için seçilmiş örnek değerlerdir. Parsel bilgileri
> (konum, alan, nitelik) ise gerçektir. Gerçek bir fiyat kaynağı bağlandığında yalnızca
> `data.py` dosyasının değişmesi yeterlidir.

## Çalıştırma

Python 3.12 gerekir.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
uvicorn app.main:app --reload
```

- Arayüz: <http://localhost:8000>
- API dokümanı (Swagger): <http://localhost:8000/docs>

Yerel ayarlar `.env` dosyasından okunur; örnek için [`.env.example`](.env.example) dosyasına bakın.
`.env` git'e gönderilmez.

### Telefondan denemek (aynı Wi-Fi)

Sunucuyu yerel ağa açın:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Bilgisayarın yerel IP adresini `ipconfig` ile öğrenin (ör. `192.168.1.34`) ve telefonda
`http://192.168.1.34:8000` adresini açın. Windows güvenlik duvarı izin isteyebilir.

"Bulunduğum yeri seç" düğmesi tarayıcı kuralı gereği yalnızca **https** üzerinde çalışır;
yerel ağda çalışmaz, yayınlanmış sürümde çalışır.

## Yayınlama (Render)

Depoda hazır bir [`render.yaml`](render.yaml) bulunur.

1. [render.com](https://render.com)'a GitHub hesabıyla giriş yapın.
2. **New → Blueprint** seçip bu depoyu bağlayın.
3. Render servisi kurar ve `https://degerix-xxxx.onrender.com` biçiminde bir adres verir. Her `git push` sonrası otomatik güncellenir.

Ücretsiz planda servis 15 dakika istek almazsa uyur; sonraki ilk açılış yaklaşık bir dakika sürer.

## Testler

```bash
pytest
```

86 test ağa çıkmadan çalışır; TKGM ve Nominatim sabit verilerle taklit edilir. Her push'ta GitHub Actions üzerinde de çalışır. Kapsanan konular:

- **Değerleme modeli:** determinizm, dökümün tutarlılığı, sorulara ve senaryolara göre değer ve aralık, güven düzeyleri
- **Coğrafi hesaplar:** mesafe, poligon merkezi ve alanı
- **Veri ayrıştırma:** TKGM'nin iki farklı sayı biçimi, nitelik metninden imar durumu tahmini
- **API:** yedek akışlar (TKGM kapalıyken ya da parsel yokken), 404/422/502 yanıtları

## API

| Metot | Yol | Açıklama |
|---|---|---|
| GET | `/api/parcels/at?lat=&lng=` | Koordinattaki parsel; kayıt yoksa OSM adresi (`source: "osm"`) |
| GET | `/api/parcels/{mahalle_id}/{ada}/{parsel}` | Ada/parsel ile parsel |
| POST | `/api/estimate` | Tahmin, döküm ve satış senaryoları (gövde aşağıda) |
| GET | `/api/provinces` · `/api/provinces/{id}/districts` · `/api/districts/{id}/neighborhoods` | İdari listeler |
| GET | `/api/search?q=` | Yer arama |
| GET | `/api/usages` | İmar durumları (`zoned`: emsal sorulur mu) |

`/api/estimate` gövdesi:

```json
{
  "province": "Muğla", "district": "Bodrum", "area_m2": 467.87, "usage": "konut",
  "lat": 37.0385, "lng": 27.419, "province_id": 70, "district_id": 724,
  "kaks": 1.5, "deed": "hisseli", "share_pct": 25, "road": "var", "utilities": "kismen"
}
```

`deed`: `tam` · `hisseli` · `bilinmiyor` — `road`: `var` · `yok` · `bilinmiyor` —
`utilities`: `var` · `kismen` · `yok` · `bilinmiyor`. Konum, kimlikler ve sorular isteğe bağlıdır.

Hata yanıtları `{"detail": "Türkçe açıklama"}` biçimindedir. Kayıt yoksa 404,
girdi geçersizse 422, dış servise ulaşılamazsa 502 döner.

## Proje yapısı

```text
app/
  main.py          FastAPI uç noktaları ve şemalar
  valuation.py     değerleme modeli (saf fonksiyonlar)
  data.py          referans fiyatlar, katsayılar, Türkçe ad eşleştirme
  geo.py           mesafe, poligon merkezi ve alanı
  tkgm.py          TKGM istemcisi + önbellek
  nominatim.py     OpenStreetMap istemcisi (hız sınırlı)
  errors.py        ortak hata tipleri
static/            arayüz (index.html, style.css, app.js)
tests/             pytest
render.yaml        Render yayın tanımı
```

## Bilinen sınırlamalar

- **TKGM API'si:** kullanılan TKGM uç noktaları parselsorgu.tkgm.gov.tr'nin herkese açık servisidir, resmî olarak belgelenmemiştir. Biçim değişebilir ve yoğun kullanımda istek sınırına takılabilir.
- **Konum katsayısı:** ilçenin coğrafi merkezini kullanır. Bu nokta her zaman şehir merkezi değildir; geniş ilçelerde (ör. Çankaya) sapma olabileceği için etki 0,85 – 1,10 bandında tutulur.
- **Nitelik ≠ imar durumu:** nitelikten tahmin edilen imar durumu yalnızca bir öneridir; gerçek imar durumu ve emsal belediyeden öğrenilmelidir.
- **Harita altlıkları:** OpenStreetMap karoları ve Esri uydu görüntüsü API anahtarı gerektirmez ama düşük trafikli kullanım içindir ([OSM karo politikası](https://operations.osmfoundation.org/policies/tiles/)). Yoğun trafikte ücretli bir karo sağlayıcısına geçilmelidir.

## Yol haritası

- **Bölge analizi:** TCMB EVDS'den il bazında konut birim m² fiyatları ve konut fiyat endeksi
- **Emsal girişi:** kullanıcının bulduğu ilan fiyatlarından bölge ortalaması

## Yasal uyarı

Değerix bir portfolyo projesidir. Sunulan tahminler bilgilendirme amaçlıdır; yatırım
tavsiyesi değildir ve SPK lisanslı gayrimenkul değerleme raporu yerine geçmez.
