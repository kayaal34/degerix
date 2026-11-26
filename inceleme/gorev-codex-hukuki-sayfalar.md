# Codex görevi — hukuki metinler ve içerik sayfaları

Düzen: [NASIL.md](NASIL.md). Notlarını en alttaki **Codex notları** başlığına yaz,
işi tek commit'te bitir. Abonelik sayfası işin iyi çıktı; bu onun devamı.

## Durum

Değerix ücretli abonelik alıyor (`d882830`, `948d7b5`, Codex `0949010`). Türkiye'de
çevrim içi ücretli hizmet satan bir sitenin hiçbir hukuki metni şu an yok. Depoda
yalnızca `index.html`, `harita.html`, `abonelik.html` var.

**Senin dosyaların (hepsi yeni):**
`static/sss.html`, `static/kvkk.html`, `static/gizlilik.html`, `static/cerez.html`,
`static/kosullar.html`, `static/mesafeli-satis.html`, `static/iptal-iade.html`,
`static/sayfa.css` (bu yedisinin ortak biçimi).

**Dokunma:** `static/index.html`, `static/harita.html`, `static/abonelik.html`,
`static/app.js`, `static/hesap.js`, `static/style.css`, `static/abonelik.css`,
`app/*`, `tests/*`, `tools/*`. Alt bilgi bağlantılarını sayfalara ben bağlayacağım;
sen yalnızca sayfaları üret.

## Uyulacak iki kural

1. **Şirket kimliği uydurulmayacak.** Ünvan, adres, MERSİS/vergi numarası, ETBİS
   kaydı, KEP adresi, telefon — hiçbiri bilinmiyor. Hepsi `[[VERİ SORUMLUSU ÜNVANI]]`,
   `[[ADRES]]`, `[[MERSİS NO]]`, `[[E-POSTA]]` gibi köşeli çift parantezli yer
   tutucu kalsın. Uydurulmuş bir adres hukuki metni sahte belgeye çevirir.
2. **Her sayfanın başında görünür bir not:** bu metinler taslaktır ve yayına
   girmeden önce avukat incelemesinden geçmelidir. İkimiz de hukukçu değiliz;
   metin iyi bir başlangıç noktasıdır, hukuki görüş değildir.

## Sayfa sayfa ne isteniyor

**`kvkk.html` — KVKK Aydınlatma Metni.** 6698 sayılı kanunun 10. maddesi
çerçevesinde: veri sorumlusunun kimliği (yer tutucu), işlenen kişisel veriler,
işleme amaçları, hukuki sebebi, aktarıldığı taraflar, saklama süresi ve 11. madde
hakları. Gerçekten işlediğimiz veriyi yaz, genel şablon değil:
- E-posta adresi ve telefon numarası (üyelik, doğrulama kodu) — Supabase'de saklanır.
- Sorgu geçmişi: il, ilçe, koordinat, ada/parsel, alan, imar durumu, çıkan değer
  (`supabase/migrations/0001_abonelik.sql` içindeki `degerix_queries` tablosu).
- Sunucu tarafında üçüncü taraflara giden ama **kişiye bağlı olmayan** istekler:
  TKGM parsel sorgusu, OpenStreetMap/Overpass, Open-Meteo yükselti, TCMB EVDS,
  Nominatim. Bunlara kullanıcı kimliği gönderilmiyor, yalnızca koordinat/parsel gidiyor.
- Veri işleyen: Supabase (barındırma, AB bölgesi), uygulama sunucusu (Render).
  Yurt dışına aktarım bu yüzden var ve metinde açıkça yazmalı.

**`gizlilik.html` — Gizlilik Politikası.** KVKK metninin günlük dille anlatımı;
hangi veri neden tutuluyor, ne kadar tutuluyor, kullanıcı nasıl sildirir. Hesap
silme ucu bende yazılıyor, sen "Hesabım sayfasından silebilirsiniz" diye yaz.

**`cerez.html` — Çerez Politikası.** Dürüst ol: sitede reklam/izleme çerezi yok.
Kullanılanlar `localStorage` üzerinden ve zorunlu/işlevsel: oturum jetonu
(`degerix.oturum`), karşılaştırma listesi, kullanıcı tercihleri. Üçüncü taraf
olarak yalnızca CDN'den font ve harita karosu geliyor (Google Fonts, jsDelivr,
OpenStreetMap, ArcGIS) — bunları da say.

**`kosullar.html` — Kullanım Koşulları / Üyelik Sözleşmesi.** Hizmetin ne olduğu
ve **ne olmadığı** en kritik kısım: Değerix lisanslı değerleme raporu üretmez,
SPK lisanslı değerleme kuruluşu değildir, çıktısı resmî işlemlerde delil değildir.
Sorumluluk sınırı, hesabın askıya alınması, otomatik toplu sorgu yasağı.

**`mesafeli-satis.html` — Mesafeli Satış Sözleşmesi + Ön Bilgilendirme Formu.**
Tek sayfada iki bölüm olabilir. Taraflar, hizmetin konusu, bedel, ödeme şekli,
süre, cayma hakkı ve **dijital hizmette cayma hakkının istisnası** (hizmet
ifasına başlandıktan sonra). Fiyatlar henüz belli değil, `abonelik.html` ile
tutarlı olsun diye rakam yazma, `[[PLAN BEDELİ]]` yer tutucusu kullan.

**`iptal-iade.html` — İptal ve İade Koşulları.** Abonelik nasıl iptal edilir,
kalan sorgu hakkına ne olur, iade hangi hâllerde yapılır.

**`sss.html` — Sıkça Sorulan Sorular.** En az 12 soru, gerçek cevaplarla. Fikir:
Değerix değeri nasıl buluyor? Veriler nereden geliyor? Tahmin ne kadar isabetli?
(README'deki ölçüm günlüğünden gerçek sayıyı al: 104 ilanda tipik sapma ×1,79,
±%50 içinde 66 kayıt — süsleme, olduğu gibi yaz.) Neden aralık veriyorsunuz?
Banka bu raporu kabul eder mi? (hayır) Ada/parsel bilmiyorum, ne yapmalıyım?
İlk üç sorgu neden ücretsiz? Verilerim ne oluyor? Hesabımı nasıl silerim?
İmarsız tarlaya neden imarlı gibi değer çıktı? Fiyat neden ilandan düşük çıkıyor?

## Biçim

`style.css` değişkenlerini (`--brand`, `--surface`, `--line`, `--muted`, `--text`)
kullan, yeni renk uydurma. `index.html` ile aynı marka başlığı ve alt bilgi dursun.
Uzun metinlerde okunur satır genişliği (65–75 karakter), içindekiler bağlantıları,
telefon genişliğinde yatay kaydırma yok. Derleme adımı yok. Her sayfaya `<title>`
ve `meta description` yaz.

## Codex notları

<!-- Ne yapıldı, neyi doğruladın, hangi yer tutucular dolduruimayı bekliyor. -->
