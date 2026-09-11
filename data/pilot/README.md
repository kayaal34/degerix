# Bursa pilot veri seti

Modeli gerçek değerlerle ayarlamak ve hata payını ölçmek için elle derlenen kayıtlar
(`bursa.csv`). Hedef: 50–150 kayıt.

## Kurallar

- Her kaydın kaynağı kamuya açık ya da izinli olmalı ve `kaynak_url` boş bırakılmamalı.
  İzinli bir emlak ofisi listesi için adres yerine `ofis:<kısa-ad>:<yıl>` gibi bir etiket yazılır.
- Kişisel veri yazılmaz: isim, telefon, kimlik numarası yok.
- İlan sitelerinden (sahibinden vb.) kayıt kopyalanmaz.

## Sütunlar

| Sütun | Açıklama |
|---|---|
| `tarih` | Değerin tarihi, `YYYY-AA-GG` |
| `ilce`, `mahalle`, `ada`, `parsel` | Parsel kimliği; bilinmeyen alan boş kalır |
| `lat`, `lng` | Parselin yaklaşık konumu |
| `alan_m2` | Yüzölçümü |
| `imar` | `konut`, `ticari`, `sanayi`, `bag_bahce`, `zeytinlik`, `tarla` |
| `emsal` | KAKS; bilinmiyorsa boş |
| `deger_tl` | Toplam değer (TL) |
| `deger_turu` | `satis` (gerçekleşen satış) · `muhammen` (ihale tahmini bedeli) · `ekspertiz` (lisanslı değerleme) · `birim_deger` (belediye arsa m² birim değeri × alan) |
| `kaynak_turu` | `belediye_ihale` · `kap_gyo` · `belediye_birim_deger` · `emlak_ofisi` |
| `kaynak_url` | Belgenin adresi |
| `not` | İsteğe bağlı açıklama |

## Bursa'da nereden bulunur

- **İhale ilanları ve sonuçları:** Bursa Büyükşehir ve ilçe belediyelerinin taşınmaz satış ihaleleri
- **KAP değerleme raporları:** Bursa'daki arsalar için GYO raporları (yalnızca m², değer, tarih ve konum alınır)
- **Belediye birim değerleri:** Nilüfer, Osmangazi, Yıldırım ve Mudanya'nın 2026–2029 arsa m² birim değer listeleri
