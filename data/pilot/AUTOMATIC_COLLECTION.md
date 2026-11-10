# Otomatik toplama: ilk kaynak

`python tools/collect_auctions.py` Orhaneli Belediyesi'nin BursaVar'da yayımlanan
15 Eylül 2026 ihale tablosunu indirir ve 9 kaydı tek seferde çıkarır.
Bu sürüm yalnızca bu tablo biçimini destekler; genel internet tarayıcısı değildir.

Çıktı: `data/source/orhaneli_review.csv` ve kaynak URL, indirme zamanı, SHA256
içeren metadata dosyası. Bunlar git dışında tutulur. Tekrar çalıştırma aynı
çıktıyı yeniler; satırlar birikerek çoğalmaz. Yerel HTML için `--html dosya.html`.

Fiyat ve yüzde 3 teminat tutarlılığı kontrol edilir. Kaynaktaki `2.500,000TL`
gibi belirsiz tutarlar boş bırakılır. Tablo 9 kayıt vermiyorsa işlem hata verir.
Kaynak engellenirse kimlik doğrulama veya erişim engeli aşılmaz.

Bu kayıtlar **muhammen bedeldir**, gerçekleşmiş satış değildir. İhale tarihi
değerleme tarihi yerine geçirilmez. Arsa niteliğinden konut imarı çıkarılmaz.
Koordinat, gerçek imar ve değerleme tarihi doğrulanmadan pilot klasörüne taşıma.
Bu nedenle mevcut kalibrasyon aracı bu çıktıyı otomatik okumaz.

Sonraki aşama: ek belediyeler için ayrı tablo adaptörleri, TKGM ile kesin
ada/parsel eşleşmesinden koordinat tamamlama ve tarih uyumlu fiyat verisi.
Eğitim/doğrulama ayrımı parsel bazında yapılmalı; muhammen bedel, ekspertiz ve
gerçek satış sonuçları ayrı raporlanmalı. Bu ilk 9 kayıt modeli eğitmek için yeterli değildir.

## TKGM koordinat tamamlama

`python tools/enrich_auction_locations.py data/source/orhaneli_review.csv --output data/source/orhaneli_enriched.csv`

İl/ilçe/mahalle adları tekil eşleşirse ada/parsel sorgulanır. Alan farkı %5'i
aşarsa koordinat yazılmaz. `300 Evler` gibi farklı yazımlar tahminle eşleştirilmez.
Sonuç geometrinin merkezidir; imar veya değerleme tarihi doğrulaması değildir.
Eşleşmeyen kayıtların nedeni `konum_durumu` sütununa yazılır.

## İkinci kaynak ve eğitim

`python -m tools.collect_treasury` e-Devlet'in herkese açık Hazine listesinin
ilk sayfasını indirir. Alanı boş olan kayıtlar boş kalır. Fiyatın gerçekleşen
satış bedeli olduğu varsayılmaz. Çıktı `data/source/treasury_review.csv`.
Bu komut tüm Hazine envanterini veya sayfaların tamamını toplamaz.

Kalibrasyon artık yalnızca `satis` türündeki kayıtlarla çalışır. Tarih, kaynak,
pozitif sonlu sayılar ve açık imar kodu gerekir. Aynı parsel tekrarlanırsa ilk
kayıt kullanılır; parsel kimliği hash'iyle yaklaşık %80 eğitim / %20 doğrulama
ayrılır. En az 10 eğitim ve 5 doğrulama parseli gerekir; bunlar kalite garantisi
değil, asgari çalıştırma eşikleridir. Sınıf başına 5 eğitim kaydı kuralı sürer.
`--uygula`, doğrulamada ortanca hatası düşmezse veya %25 içinde kalanların oranı
azalırsa dosyayı değiştirmez. Son rapor son katsayıları yeniden ölçer.

Güncel konut fiyatı kopyası kullanıldığı için eski satışları tarih düzeltmesi
yapmadan karıştırmayın. Bu sürüm tarihsel fiyat normalizasyonu sağlamaz.
İlk toplanan 29 ihale inceleme kaydı bu nedenle eğitim klasörlerine taşınmadı.
