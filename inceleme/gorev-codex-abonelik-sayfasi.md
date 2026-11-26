# Codex görevi — abonelik / plan sayfası

Düzen: [NASIL.md](NASIL.md). Bu dosyanın altındaki **Codex notları** başlığına
yazar, işi tek commit'te bitirirsin. Son rapor Claude'da.

## Neden sende

Değerix abonelikli oluyor. Sunucu tarafı ve giriş akışı bende bitti (`d882830`,
`948d7b5`). Eksik olan tek şey, ödeme duvarının gönderdiği sayfa. O sayfa
tamamen ayrı duruyor, benim dokunduğum dosyalarla çakışmıyor.

**Senin dosyaların:** `static/abonelik.html` (yeni), `static/abonelik.css` (yeni).
**Dokunma:** `static/harita.html`, `static/app.js`, `static/hesap.js`,
`static/style.css`, `app/*`, `tests/*`. Bunların hepsi bende açık.

## Ne var elinde

- `harita.html` içindeki ödeme duvarı `<a href="abonelik.html">Planlara bak</a>`
  diyor; sayfa henüz yok, bağlantı boşa düşüyor.
- `GET /api/account` oturum ve hak durumunu döner:
  `{uyelik, oturum, eposta, telefon, ucretsiz_hak, ucretsiz_kalan, abonelik:{plan,bitis,hak,kalan}|null, sorgu_hakki_var}`.
  Üyelik kapalıyken yalnızca `{uyelik:false}` döner — sayfa o durumda da
  kırılmadan açılmalı.
- Oturum jetonu `localStorage["degerix.oturum"]` içinde; `hesap.js` modülünü
  `import * as hesap from "./hesap.js"` ile alıp `hesap.jeton()` çağırabilirsin.
  O dosyayı **değiştirme**, yalnızca kullan.
- Planların fiyatı ve adı henüz kararlı değil; `supabase/migrations/0001_abonelik.sql`
  içinde `plan` alanı `'aylik' | 'yillik' | 'paket'` olarak duruyor. Sayfayı bu üç
  plan üzerine kur, fiyatları tek bir JS nesnesinde topla ki sonra tek yerden değişsin.

## İstenen

1. **Plan kartları** — üç plan, her birinde ne kadar sorgu hakkı verdiği, fiyatı,
   kime uygun olduğu. Ücretsiz katman da görünsün: üç sorgu, kayıtla.
2. **Durum şeridi** — sayfanın üstünde kullanıcının bugünkü hâli: giriş yapmamışsa
   "giriş yap" çağrısı, yapmışsa kalan hakkı ve varsa aboneliğinin bitiş tarihi.
3. **Ödeme henüz yok.** Sağlayıcı seçilmedi (iyzico muhtemel). "Satın al" düğmesi
   şimdilik `data-plan` taşısın ve tıklanınca "ödeme altyapısı bağlanıyor" diyen
   bir bilgi göstersin. Sahte bir ödeme akışı **kurma**, kimseye kart alanı gösterme.
4. **Yasal metin** — sayfanın altında: Değerix'in verdiği şeyin lisanslı değerleme
   raporu olmadığı, resmî işlemlerde delil sayılmadığı. `harita.html` içindeki
   `.print-uyari` paragrafı aynı metnin uzun hâli, oradan al, kopyala-yapıştır değil
   sayfaya uygun kısalt.
5. **Biçim** — `style.css` içindeki değişkenleri (`--brand`, `--surface`, `--line`,
   `--muted`) kullan, kendi renklerini uydurma. `index.html` ve `harita.html`
   başlıklarıyla aynı marka bloğu dursun. Telefon genişliğinde yatay kaydırma olmasın.
   Derleme adımı yok: düz HTML, CSS ve gerekiyorsa modül JS.

## Dikkat

- Sayfa **oturum olmadan da açılmalı**; `/api/account` 200 dönmezse ya da
  `uyelik:false` ise plan kartları yine görünsün, durum şeridi sessizce gizlensin.
- Fiyatları TL yaz, `Intl.NumberFormat("tr-TR")` kullan.
- Testleri `tests/` altına ekleme — orası bende. Sayfanın çalıştığını kendi
  tarafında tarayıcıda doğrula ve ne gördüğünü aşağıya yaz.

## Codex notları

Tamamlandı. `static/abonelik.html` ve `static/abonelik.css` eklendi. Ödeme duvarındaki mevcut bağlantı yeni sayfayı açıyor. Ücretsiz başlangıç ve üç plan kartı, hesap durumundan bağımsız gösteriliyor. Hesap şeridi mevcut `hesap.js` modülünden oturumu ve kalan hakları okuyor. Giriş bağlantısı, mevcut giriş arayüzünün bulunduğu haritayı açıyor.

Fiyat ve sorgu kotaları ürün kararı verilene kadar “açıklanacak” olarak gösteriliyor. Plan düğmesi satışın henüz açılmadığını duyuruyor.

Yerel FastAPI üzerinde Chromium ile 320, 390, 768 ve 1440 px genişliklerde yatay taşma, klavyeyle plan eylemi ve ödeme duvarı bağlantısı doğrulandı. Hesap kapalı durumu gerçek yerel API ile çalıştırıldı. 503, oturumsuz, oturumlu kota ve bitiş tarihi temsili API yanıtlarıyla sınandı. Canlı Supabase doğrulaması bu çalışmanın dışında kaldı.
