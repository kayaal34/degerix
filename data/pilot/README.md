# Kalibrasyon verisi

Model katsayıları (`app/model_params.py`) başlangıç varsayımıdır. Burada toplanan
gerçek kayıtlarla ölçülüp ayarlanırlar:

```bash
python tools/calibrate.py            # hata raporu
python tools/calibrate.py --uygula   # katsayıları app/static_data/calibration.json içine yazar
```

İki klasör okunur:

| Klasör | İçerik | Git'e girer mi? |
|---|---|---|
| `data/pilot/` | Kaynağı kamuya açık kayıtlar: belediye ihaleleri, KAP değerleme raporları, belediye arsa birim değerleri | **Evet** |
| `data/private/` | İlan sitelerinden elle derlenen doğrulama kayıtları | **Hayır** (`.gitignore`) |

## Kurallar

- **Ham ilan verisi yayımlanmaz.** İlan kayıtları yalnızca `data/private/` içinde kalır; depoya sadece kalibrasyon sonucu katsayılar girer.
- **Kişisel veri yazılmaz:** isim, telefon, kimlik numarası yok.
- `data/pilot/` için `kaynak_url` zorunludur. İzinli bir emlak ofisi listesinde adres yerine `ofis:<kısa-ad>:<yıl>` etiketi yazılır.
- **İlan fiyatı satış fiyatı değildir.** `deger_turu` sütununa `ilan` yazıldığında kalibrasyon, `model_params.asking_discount` kadar pazarlık payı düşerek karşılaştırır.

## Sütunlar

Zorunlu: `il`, `lat`, `lng`, `alan_m2`, `imar`, `deger_tl`, `deger_turu`

| Sütun | Açıklama |
|---|---|
| `tarih` | Değerin tarihi, `YYYY-AA-GG` |
| `il` | Parselin ili; konut fiyatı buradan alınır (ör. `Bursa`) |
| `ilce`, `mahalle`, `ada`, `parsel` | Parsel kimliği; bilinmeyen alan boş kalır |
| `lat`, `lng` | Parselin konumu (ondalık derece) |
| `alan_m2` | Yüzölçümü |
| `imar` | `konut` · `ticari` · `sanayi` · `bag_bahce` · `zeytinlik` · `tarla` |
| `emsal` | KAKS; bilinmiyorsa boş |
| `deger_tl` | Toplam değer (TL) |
| `deger_turu` | `satis` (gerçekleşen satış) · `ilan` (istek fiyatı) · `muhammen` (ihale tahmini bedeli) · `ekspertiz` (lisanslı değerleme) · `birim_deger` (belediye arsa m² birim değeri × alan) |
| `tapu` | `tam` · `hisseli` · boş |
| `yol` | `var` · `yok` · boş |
| `elektrik_su` | `var` · `kismen` · `yok` · boş |
| `manzara` | `var` · `yok` · boş |
| `kose` | `evet` · `hayir` · boş |
| `sulama` | `sulu` · `kuru` · boş (yalnızca imarsız arazide) |
| `kaynak_turu` | `belediye_ihale` · `kap_gyo` · `belediye_birim_deger` · `emlak_ofisi` · `ilan` |
| `kaynak_url` | Belgenin adresi (pilot kayıtlarda zorunlu) |
| `not` | İsteğe bağlı açıklama |

## Kayıt nereden bulunur

- **Belediye ihale ilanları ve sonuçları:** ada/parsel ve muhammen bedelle yayımlanır
- **KAP değerleme raporları:** gayrimenkul yatırım ortaklıklarının SPK lisanslı raporları (yalnızca m², değer, tarih ve konum alınır)
- **Belediye arsa birim değerleri:** 2026–2029 dönemi için sokak bazında belirlenen emlak vergisi değerleri
- **Doğrulama için ilanlar:** yalnızca `data/private/` klasöründe

## Hedef

İlk aşama Bursa (`bursa.csv`): 50–150 kayıt. Bir yerleşim sınıfının katsayısının
ayarlanması için o sınıfta en az 5 kayıt gerekir; altındaki sınıflara dokunulmaz.
