# Supabase kurulumu

Üyelik ve sorgu hakları Supabase üzerinde çalışıyor. Bu dosya, sıfırdan
çalışır hâle getirmenin tam adımlarını veriyor. Yaklaşık on beş dakika.

Kurulum yapılana kadar uygulama **üyeliksiz** çalışır: değerleme sınırsızdır,
giriş ekranı "üyelik bu kurulumda kapalı" der. Yani yarım bırakılmış bir
kurulum siteyi bozmaz.

## 0. Önce bilinmesi gerekenler

- **Ayrı e-posta hesabı açmanıza gerek yok.** Supabase GitHub ile giriş kabul
  ediyor; mevcut GitHub hesabınız yeterli.
- **Ücretsiz plan yeter.** Sınır: iki ücretsiz proje. Zaten iki projeniz varsa
  Supabase yenisini açtırmaz; önce kullanılmayan birini silmeniz gerekir.
- **Kredi kartı istemiyor.**
- Uygulamanın kullandığı tek anahtar `anon` (herkese açık) anahtardır.
  `service_role` anahtarına ihtiyaç yok ve hiçbir yere konmamalı: o anahtar
  bütün satır güvenliği kurallarını atlar, sunucuya koyulursa bir sızıntı
  bütün kullanıcıların verisini açar.

## 1. Hesap ve proje

1. <https://supabase.com> → **Start your project** → **Continue with GitHub**.
2. **New project**:
   - **Name:** `degerix`
   - **Database password:** güçlü bir parola üretin ve **saklayın**
     (bu parolayı uygulama kullanmıyor ama veritabanına doğrudan bağlanmak
     gerekirse tek yol odur, kaybolursa sıfırlamak gerekir)
   - **Region:** `Central EU (Frankfurt)` — kullanıcılar Türkiye'de, en yakın
     bölge bu. KVKK metni de yurt dışı aktarımın AB'ye olduğunu yazıyor;
     başka bölge seçerseniz o metni de güncelleyin.
3. Proje kurulana kadar bir iki dakika bekleyin.

## 2. Tabloları ve işlevleri kur

**SQL Editor** → **New query**. Şu iki dosyanın içeriğini **sırayla** yapıştırıp
çalıştırın:

1. `supabase/migrations/0001_abonelik.sql` — profiller, abonelikler, sorgu
   kayıtları, sorgu hakkı işlevleri, satır güvenliği kuralları.
2. `supabase/migrations/0002_kvkk_haklari.sql` — veri indirme, geçmiş
   temizleme, hesap silme işlevleri.

Hata vermeden bitmeli. İkinciyi birinciden önce çalıştırırsanız hata alırsınız.

## 3. Doğrulama kodu e-postayla gelsin

**Bu adım atlanırsa giriş ekranı çalışmaz.** Supabase varsayılan olarak
e-postaya *bağlantı* gönderir; uygulama ise altı haneli *kod* istiyor.

**Authentication → Emails → Magic Link** şablonunda `{{ .ConfirmationURL }}`
yerine `{{ .Token }}` kullanın. Örnek:

```html
<h2>Değerix giriş kodunuz</h2>
<p>Kod: <b>{{ .Token }}</b></p>
<p>Kodu istemediyseniz bu e-postayı yok sayın.</p>
```

**Authentication → Providers → Email** açık olmalı.

> Ücretsiz planda Supabase'in kendi e-posta gönderimi saatte birkaç mesajla
> sınırlıdır ve istenmeyen klasörüne düşebilir. Gerçek kullanıcı gelmeye
> başlayınca **Authentication → Emails → SMTP Settings** altından kendi SMTP
> sağlayıcınızı bağlayın. Test için varsayılan yeterli.

## 4. Anahtarları al

**Project Settings → API**:

- **Project URL** → `SUPABASE_URL`
- **anon public** → `SUPABASE_ANON_KEY`

`service_role` anahtarını kopyalamayın.

## 5. Uygulamaya ver

Yerelde, depo kökündeki `.env` dosyasına:

```
SUPABASE_URL=https://xxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
```

Render'da: **Dashboard → degerix → Environment** → aynı iki değişken →
**Save**, servis yeniden başlar.

## 6. Çalıştığını doğrula

1. `/api/account` → `{"uyelik": true, ...}` dönmeli. `false` dönüyorsa
   değişkenler okunmuyor demektir.
2. `/giris.html` → form görünmeli ("üyelik bu kurulumda kapalı" yazmamalı).
3. Kendi e-postanızla kod isteyin, gelen kodla girin.
4. `/hesabim.html` → plan, kalan hak ve boş sorgu geçmişi görünmeli.
5. Bir değerleme yapın, `/hesabim.html`'e dönün: sorgu geçmişte görünmeli ve
   kalan hak bir azalmalı.
6. **Hesabım → Verilerimi indir** ve **Hesabı sil** düğmelerini kendi test
   hesabınızda bir kez deneyin. KVKK metninde bu haklar vaat ediliyor;
   çalıştığını görmeden yayına almayın.

## Sorun giderme

| Belirti | Sebebi |
|---|---|
| Giriş ekranı "üyelik kapalı" diyor | `SUPABASE_URL` / `SUPABASE_ANON_KEY` okunmuyor |
| E-postada kod yok, bağlantı var | 3. adım yapılmamış (`{{ .Token }}`) |
| Kod geliyor ama "doğrulanamadı" | Kodun süresi dolmuş (varsayılan 1 saat) ya da yanlış e-posta |
| Değerleme 401 veriyor | Oturum açılmamış; normal davranış |
| Değerleme 402 veriyor | Ücretsiz üç hak bitmiş; normal davranış |
| Sorgu geçmişi boş kalıyor | `0001_abonelik.sql` çalıştırılmamış |
