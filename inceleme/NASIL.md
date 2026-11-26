# İnceleme düzeni

Bu klasör iki model arasındaki inceleme yazışmasıdır: Codex inceler, Claude cevap
verir, kabul edilenler commit edilir. Kurulum yok; köprü deponun kendisi.

## Akış

1. **Codex** incelemesini `inceleme/codex-<YYYY-AA-GG>.md` dosyasına yazar ve commit eder.
2. **Claude** dosyayı okur, her maddenin altına cevabını yazar, kabul ettiği
   maddeleri düzeltip commit eder ve cevabın yanına commit hash'ini bırakır.
3. İkinci tur gerekiyorsa Codex aynı dosyanın altına ekler; dosya büyür, tarih değişmez.

4. Yazışma kapandığında **son raporu Claude yazar**: aynı dosyanın sonuna
   "Sonuç" başlığı — kabul edilen maddeler ve commit'leri, reddedilenler ve
   gerekçeleri, ölçülmeden karara bağlanamayan açık sorular.

Karşı taraf değişiklikleri görmek için `git pull` yapar. Her tur commit edilir ki
yazışma kayda geçsin.

İki modelin işi birbirinin açığını kapatmak: Codex koda ve yönteme dışarıdan
bakar, Claude ölçümü koşturup kararı verir ve gerekçeyi yazar. Bir bulgu
"ölçülebilir" hâle geldiği anda tartışma biter — betik koşulur, sayı ne diyorsa o olur.

## Madde biçimi

Codex her bulguyu numaralı başlıkla yazar:

```markdown
## 3. Normalizasyon ortancayı iki kez bölüyor

**Dosya:** tools/cevre_olc.py:140
**Önem:** yüksek | orta | düşük
**Bulgu:** (ne yanlış, hangi girdide ne olur)
```

Claude aynı maddenin altına ekler:

```markdown
**Cevap (Claude):** Kabul | Red | Kısmen — gerekçe tek paragraf.
**Commit:** abc1234 (kabul edildiyse)
```

## İnceleme ölçütü

Bu projede bir sayı ölçülmeden modele girmez ve ölçüm "etki yok" diyorsa kodda
kalmaz. Ölçüm iddialarını sorgulamak incelemenin asıl işidir: yöntem hatası,
sızdıran doğrulama (kaydın kendisinin katsayıyı kurmaya katılması), az kayıtlı
kovadan genelleme, ortalamayı iki aykırı kaydın taşıması. Bulgu "şu girdide şu
çıkar" diye somutlanırsa cevabı da ölçülebilir olur.
