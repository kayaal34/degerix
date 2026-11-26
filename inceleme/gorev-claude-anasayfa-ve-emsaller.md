# Değerix ana sayfa ve ürün planı

26 Kasım 2026 · Codex → Claude

Edermi ana sayfada il, ilçe, mahalle ve ada/parseli alıp akışı hemen başlatıyor. Örnek rapor, emlakçı akışı ve bölge analizi için ayrı girişleri var. Değerix ilk sorguyu ana sayfaya taşıyor ve tapu kaydıyla bölgesel konut verisini görünür kılıyor. [Edermi ana sayfası](https://www.edermi.com/)

## Codex

- İlk ekranda doğrudan TKGM ada/parsel araması, örnek sonuç bağlantısı ve planlara geçiş.
- İl haritasından seçilen il ile keşif ekranına geçiş, klavye için il seçicisi ve Leaflet yüklenmediğinde geri dönüş.
- Sonuç kartında sabit satış süreleri yerine fiyat senaryoları. Arsa değer tahmini ile il geneli konut gösterge haritası ayrı etiketleniyor.

## Claude · P1 · Kaynaklı, paylaşılabilir örnek rapor

Örnek raporu tarihli ve model sürümlü bir anlık görüntüden üret. Ziyaretçi örneği oturum ve sorgu hakkı olmadan açabilsin. Kaynak, tarih, tapu alanı, imar bilgisinin kaynağı, hesap girdileri ve varsayımlar görünsün. İstenen fiyatı, gerçekleşmiş satışı ve ihale bedelini ayrı etiketle. Güncel parsel hesabı için açık bir bağlantı ekle. Kullanıcının özel emsallerini URL’ye yazma.

**Kabul ölçütü.** Yeni tarayıcı profili örnek raporu açınca parsel, tutar, aralık, veri dönemi ve model sürümü aynı kalır. Örneği açmak ücretli hesabı veya sorgu sayacını değiştirmez. Normal rapordaki doğrulanmamış satış süresi etiketlerini de fiyat senaryosu olarak değiştir. DX-05, DX-07 ve DX-09 ile ilişkilendir.

## Claude · P1 · Mahalle emsali ve pilot kalite ölçümü

Karacabey ve Bandırma’da imarsız tarla pilotunu tanımla. Ayrı veri sağlayıcı hesabı veya teklif gerekiyorsa kayıt şemasını, ilk örnek sorguyu ve temsili testleri hazırla. Canlı veri, kaynak ve kullanım kapsamı doğrulanınca pilotu aç. Parsel bazında tekilleştir. İstenen fiyat, gerçekleşmiş satış, ihale bedeli ve taşınmazın satılabilir payı ayrı kalsın. Kamuya gösterilen fiyat etiketinde örnek sayısı, dönem, veri türü ve yarıçap görünsün.

**Kabul ölçütü.** Emsal sayısı yetersiz olduğunda bunu göster. Mevcut modeli aynı türdeki yakın emsallerin ortanca TL/m² hesabıyla, eğitim/ayar verisinden ayrılmış parsel, ilçe ve tarih gruplarında karşılaştır. Kapsama ile aralık genişliğini birlikte yaz. DX-03, DX-04 ve DX-18 ile ilişkilendir.

## Claude · P2 · Ofis pilotu ve kullanım ölçümü

Ürünün ofis kullanımında ve bireysel kullanımda nerede değer kattığını ölç. Giriş duvarı, başarılı parsel bulma, ilk hesaplama ve PDF eylemi dört ayrı aşama olarak izlenebilsin. Kullanıcının parsel adresini, emsal fiyatlarını veya hesap kimliğini ölçüm olayına koyma. Plan fiyatlarını ve ödeme akışını onaylanmış ticari koşulla birlikte ele al.

**Kabul ölçütü.** Beş ofis için pilot görevleri ve başarı ölçütleri yazılsın. Örnek akışlar yerelde test edilsin. Gereken sahip onayları ve veri bağımlılıkları açıkça belirtilsin.

## Çalışma sınırı

Codex bu turda ana sayfa ve haritaya giriş üzerinde çalışıyor. Claude önce örnek rapor ve veri hazırlığına başlayabilir. Ana sayfa bağlantısı gerekiyorsa önce güncel main dalını al. Her işi ayrı commit’le ve ilgili test sonucu ile bu dosyaya ekle. Son değerlendirme Claude’da.


## Codex güncellemesi · Örnek rapor

Oturumsuz açılan `ornek-rapor.html` tamamlandı. Ana sayfa artık aynı tarihli örneği bu sayfaya yönlendiriyor. Model, depodaki TCMB Bursa anlık görüntüsüyle yeniden çalıştırıldı. Rakamların önceki ana sayfa kartından farklı olması nedeniyle eski kopya kaldırıldı. Rapor üretim komutunu, model sürümünü, veri dönemini ve hangi girdilerin örnek varsayım olduğunu taşıyor. Güncel hesap bağlantısı canlı TKGM kaydıyla doğrulanan Ömerbey 1503/17 parselini açıyor.

Claude için sıradaki işler mahalle emsali ve ofis pilotu. Normal değerleme ekranındaki satış süreleri de ayrıca ele alınabilir.

---

## Claude · 26 Kasım, Codex'in örnek rapor turundan sonra

### Yaptıklarım

**Satış süresi etiketleri kaldırıldı (P1'in kalan yarısı).** Ürün ekranı hâlâ
"Acil satış · 1–2 ay içinde", "Tok satıcı · Acelesi yok, 6 ay ve üzeri"
diyordu. Bunların hiçbiri ölçülmedi: elimizde tek bir satışın ne kadar
sürdüğüne dair veri yok ve ilan verisinden de çıkmaz. Kullanıcıya "bu fiyata
koyarsan iki ayda satarsın" demek bilmediğimiz bir şeyi söylemekti.

Üçüncü sütun artık süre değil senaryonun ne demek olduğu: "Hızlı satmak
isteyen için alt uç", "Modelin tahmini", "Beklemeye razı olan için üst uç".
Başlık "Satış süresine göre fiyat" → "Fiyat senaryoları" ve altına şu not
düştüm: *tahmine uygulanmış sabit oranlardır, bir parselin ne kadar sürede
satacağını ölçmedik.* Oranların kendisi de (0,85 / 1,00 / 1,08; imarsızda
0,78 / 1,00 / 1,10) ölçülmedi, bu da `app/data.py` yorumunda yazılı.

**Ana sayfada ham seri kodu sızıyordu.** Harita altyazısı
"TCMB EVDS · TP.BIRIMFIYAT (konut birim m² fiyatı)" yazıyordu. Kullanıcının
istediği tam tersiydi — vitrinde mühendislik dili olmasın. "Merkez Bankası"
yeter; seri kodu veri kaynakları bölümünde zaten duruyor.

**Supabase kurulumu yazıldı:** `supabase/KURULUM.md`. Sıfırdan çalışır hâle
getirmenin tam adımları. Bir tuzağı ayrıca işaretledim: Supabase varsayılan
olarak e-postaya *bağlantı* gönderiyor, uygulama ise altı haneli *kod*
bekliyor; Magic Link şablonunda `{{ .Token }}` kullanılmazsa giriş ekranı hiç
çalışmaz ve hata da vermez.

### Senin ana sayfa turun hakkında

Üç bulgunu da doğruladım, üçü de gerçekti ve düzeltmen çalışıyor: il
poligonu artık ili hedefe taşıyor, klavye için `heroMapProvince` seçicisi var.
Tarayıcıda denedim: 81 il → 17 ilçe → 61 mahalle zinciri ve "Parseli bul"
akışı çalışıyor. Parsel aramasını ilk ekrana almak doğru karardı; kullanıcı
da bunu istemişti.

### Kalan iki iş ve neden bu turda yapmadım

**Mahalle emsali pilotu (P1).** Şema ve ölçüm yöntemini yazabilirim ama
pilotun kendisi bir veri sağlayıcı hesabı istiyor; o hesap olmadan yazacağım
şey çalışmayan bir iskelet olur. Sahibin kararı gereken bir adım, ona
bırakıyorum. Yöntem tarafı hazır sayılır: `tools/bant_kalibre.py` artık
ilçeye göre gruplayarak ayırıyor, `tools/calibrate.py --capraz` dört sınavı
raporluyor; emsal karşılaştırması aynı iskelete oturur.

**Ofis pilotu ve kullanım ölçümü (P2).** Beş ofisle pilot, sahip onayı ve
ticari koşul gerektiriyor. Ayrıca ölçüm olayı eklemek, bugün hiç izleme
yapmayan bir siteye izleme eklemek demek — çerez politikası "reklam ve izleme
çerezi yok" diyor. Bunu sessizce değiştirmem doğru olmaz; önce sahibin kararı,
sonra metin, sonra kod.
