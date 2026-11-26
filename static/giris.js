/* Ayrı giriş ekranı.
 *
 * Haritadaki pencereyle aynı akışı kullanır ama kendi sayfasında: paylaşılan
 * bir bağlantı doğrudan buraya düşebilsin, tarayıcı parolayı kaydedebilsin ve
 * kullanıcı "ne için kaydoluyorum" sorusunun cevabını yanında görsün.
 *
 * hesap.js'in dışa açtığı işlevleri çağırır, kendi ağ kodunu yazmaz:
 * doğrulama akışı tek yerde kalsın, iki kopya birbirinden ayrı düşmesin.
 */

import * as Hesap from "./hesap.js";

const $ = (seçici) => document.querySelector(seçici);

const kutular = {
  kapali: $("#uyelikKapali"),
  giris: $("#gIcerik"),
  girisli: $("#girisliyiz"),
};

function göster(hangi) {
  for (const [ad, kutu] of Object.entries(kutular)) {
    if (kutu) kutu.hidden = ad !== hangi;
  }
}

function hata(mesaj) {
  const kutu = $("#gHata");
  kutu.textContent = mesaj;
  kutu.hidden = !mesaj;
}

function meşgul(düğme, çalışıyor, etiket) {
  düğme.disabled = çalışıyor;
  düğme.textContent = çalışıyor ? "Gönderiliyor…" : etiket;
}

/* Giriş sonrası nereye? Sayfaya ?devam=... ile gelinmişse oraya, yoksa
   haritaya. Açık yönlendirme açığı olmasın diye yalnızca kendi sayfalarımız
   kabul ediliyor: dışarıdan gelen bir adres buraya yazılıp kullanıcı başka
   bir siteye atılamasın. */
const İZİNLİ_DEVAM = new Set([
  "harita.html", "hesabim.html", "abonelik.html", "index.html", "./", "",
]);

function devamAdresi() {
  const istenen = new URLSearchParams(location.search).get("devam") || "";
  const temiz = istenen.replace(/^\/+/, "");
  return İZİNLİ_DEVAM.has(temiz) ? (temiz || "harita.html") : "harita.html";
}

function girişliÇiz() {
  const hak = Hesap.hak();
  const kimlik = hak?.kimlik || hak?.eposta || "";
  $("#kimlikSatiri").textContent = kimlik
    ? `${kimlik} olarak giriş yaptınız.`
    : "Bu tarayıcıda açık bir oturumunuz var.";
  göster("girisli");
}

async function kur() {
  const açık = await Hesap.kur();
  if (!açık) {
    göster("kapali");
    return;
  }
  if (await Hesap.jeton()) {
    girişliÇiz();
    return;
  }
  göster("giris");
  $("#gTelefon").focus();
}

$("#gFormKod").addEventListener("submit", async (olay) => {
  olay.preventDefault();
  hata("");
  const telefon = $("#gTelefon").value.trim();
  const eposta = $("#gEposta").value.trim();
  if (!telefon || !eposta) {
    hata("Telefon ve e-posta gerekli.");
    return;
  }
  const düğme = $("#btnKodGonder");
  meşgul(düğme, true, "Kod gönder");
  try {
    await Hesap.kodGonder({ telefon, eposta });
    $("#kodBilgi").textContent = `${eposta} adresine altı haneli bir kod gönderdik. ` +
      "Gelmezse istenmeyen klasörüne bakın.";
    $("#adim1").hidden = true;
    $("#adim2").hidden = false;
    $("#gKod").focus();
  } catch (sorun) {
    hata(sorun?.message || "Kod gönderilemedi. Birazdan tekrar deneyin.");
  } finally {
    meşgul(düğme, false, "Kod gönder");
  }
});

$("#gFormDogrula").addEventListener("submit", async (olay) => {
  olay.preventDefault();
  hata("");
  const kod = $("#gKod").value.trim();
  if (!kod) {
    hata("Kodu girin.");
    return;
  }
  const düğme = $("#btnDogrula");
  meşgul(düğme, true, "Doğrula ve gir");
  try {
    await Hesap.kodDogrula({
      telefon: $("#gTelefon").value.trim(),
      eposta: $("#gEposta").value.trim(),
      kod,
    });
    window.location.href = devamAdresi();
  } catch (sorun) {
    hata(sorun?.message || "Kod doğrulanamadı. Kodu kontrol edip tekrar deneyin.");
    meşgul(düğme, false, "Doğrula ve gir");
  }
});

$("#btnGeri").addEventListener("click", () => {
  hata("");
  $("#adim2").hidden = true;
  $("#adim1").hidden = false;
  $("#gEposta").focus();
});

$("#btnCikisYap").addEventListener("click", () => {
  Hesap.cikis();
  göster("giris");
  $("#gTelefon").focus();
});

kur().catch((sorun) => {
  göster("giris");
  hata("Hesap servisine ulaşılamadı. Birazdan tekrar deneyin.");
  console.warn("Giriş ekranı:", sorun);
});
