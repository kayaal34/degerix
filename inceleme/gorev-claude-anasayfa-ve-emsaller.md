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

