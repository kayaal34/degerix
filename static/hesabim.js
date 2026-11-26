/* Hesabım: abonelik durumu, sorgu geçmişi ve KVKK 11. madde hakları.
 *
 * Aydınlatma metni yazmak kolay; bu sayfa metinde söz verilen hakların
 * gerçekten işlediği yer. Verinin tamamı indirilebiliyor, geçmiş
 * temizlenebiliyor, hesap silinebiliyor.
 */

import * as hesap from "./hesap.js";

const $ = (seçici) => document.querySelector(seçici);
const tarih = new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" });
const para = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 });
const tamsayı = new Intl.NumberFormat("tr-TR");

let ayarlar = { url: "", anonKey: "" };

function bölüm(ad, görünür) {
  const kutu = $(ad);
  if (kutu) kutu.hidden = !görünür;
}

function bilgi(mesaj, tür = "bilgi") {
  const kutu = $("#hesapMesaj");
  kutu.textContent = mesaj;
  kutu.dataset.tur = tür;
  kutu.hidden = !mesaj;
}

/* ---------- durum ---------- */

async function durumuCiz() {
  const h = await hesap.hakYenile();
  const girisli = Boolean(h?.oturum);
  bölüm("#girisGerek", !girisli);
  bölüm("#hesapIcerik", girisli);
  if (!girisli) return null;

  $("#kimlikEposta").textContent = h.eposta ?? "—";
  $("#kimlikTelefon").textContent = h.telefon ?? "Kayıtlı değil";

  const satırlar = [
    ["Ücretsiz hak", `${h.ucretsiz_kalan} / ${h.ucretsiz_hak} sorgu kaldı`],
  ];
  if (h.abonelik) {
    satırlar.push(["Plan", h.abonelik.plan]);
    satırlar.push(["Kalan sorgu", h.abonelik.kalan == null ? "Sınırsız" : `${h.abonelik.kalan}`]);
    if (h.abonelik.bitis) satırlar.push(["Bitiş", tarih.format(new Date(h.abonelik.bitis))]);
  } else {
    satırlar.push(["Plan", "Abonelik yok"]);
  }
  $("#planListe").replaceChildren(...satırlar.flatMap(([terim, değer]) => {
    const dt = document.createElement("dt");
    dt.textContent = terim;
    const dd = document.createElement("dd");
    dd.textContent = değer;
    return [dt, dd];
  }));
  return h;
}

/* ---------- geçmiş ---------- */

async function gecmisiCiz() {
  const jeton = await hesap.jeton();
  if (!jeton || !ayarlar.url) return;
  let kayıtlar = [];
  try {
    const yanıt = await fetch(
      `${ayarlar.url}/rest/v1/degerix_queries?select=created_at,province,district,parcel,area_m2,usage,unit_price,total,source&order=created_at.desc&limit=50`,
      { headers: { apikey: ayarlar.anonKey, Authorization: `Bearer ${jeton}` } });
    if (yanıt.ok) kayıtlar = await yanıt.json();
  } catch {
    /* geçmiş okunamadı: sayfanın geri kalanı yine çalışsın */
  }

  const gövde = $("#gecmisGovde");
  if (!kayıtlar.length) {
    gövde.replaceChildren();
    bölüm("#gecmisBos", true);
    bölüm("#gecmisTablo", false);
    return;
  }
  bölüm("#gecmisBos", false);
  bölüm("#gecmisTablo", true);
  gövde.replaceChildren(...kayıtlar.map((k) => {
    const tr = document.createElement("tr");
    const yer = [k.province, k.district].filter(Boolean).join(" / ") || "Künyesi temizlendi";
    const hücreler = [
      tarih.format(new Date(k.created_at)),
      k.parcel ? `${yer} · ${k.parcel}` : yer,
      k.area_m2 ? `${tamsayı.format(k.area_m2)} m²` : "—",
      k.total ? para.format(k.total) : "—",
      k.source === "free" ? "Ücretsiz" : "Abonelik",
    ];
    for (const metin of hücreler) {
      const td = document.createElement("td");
      td.textContent = metin;
      tr.append(td);
    }
    return tr;
  }));
}

/* ---------- KVKK hakları ---------- */

async function istek(yol, ayar = {}) {
  const jeton = await hesap.jeton();
  const yanıt = await fetch(yol, {
    ...ayar,
    headers: { ...(ayar.headers ?? {}), Authorization: `Bearer ${jeton}` },
  });
  if (!yanıt.ok) throw new Error("İşlem tamamlanamadı, birazdan tekrar deneyin.");
  return yanıt;
}

async function veriIndir() {
  bilgi("Verileriniz hazırlanıyor…");
  try {
    const yanıt = await istek("/api/account/data");
    const metin = JSON.stringify(await yanıt.json(), null, 2);
    const bağlantı = document.createElement("a");
    bağlantı.href = URL.createObjectURL(new Blob([metin], { type: "application/json" }));
    bağlantı.download = "degerix-verilerim.json";
    bağlantı.click();
    URL.revokeObjectURL(bağlantı.href);
    bilgi("Verilerinizin tamamı indirildi.");
  } catch (sorun) {
    bilgi(sorun.message, "hata");
  }
}

async function gecmisiTemizle() {
  if (!confirm("Sorgu geçmişinizin künyesi silinecek: hangi parseli sorduğunuz kaydı kalmayacak. "
    + "Kullandığınız sorgu sayısı korunur. Devam edilsin mi?")) return;
  try {
    const sonuç = await (await istek("/api/account/history", { method: "DELETE" })).json();
    bilgi(`${sonuç.temizlenen ?? 0} kaydın künyesi silindi.`);
    await gecmisiCiz();
  } catch (sorun) {
    bilgi(sorun.message, "hata");
  }
}

async function hesabiSil() {
  const onay = prompt('Hesabınız ve bütün kayıtlarınız kalıcı olarak silinecek. '
    + 'Bu işlem geri alınamaz. Onaylamak için SİL yazın:');
  if ((onay ?? "").trim().toLocaleUpperCase("tr-TR") !== "SİL") {
    bilgi("Silme iptal edildi.");
    return;
  }
  try {
    await istek("/api/account", { method: "DELETE" });
    hesap.cikis();
    bilgi("Hesabınız ve bütün verileriniz silindi.");
    setTimeout(() => { location.href = "./"; }, 2500);
  } catch (sorun) {
    bilgi(sorun.message, "hata");
  }
}

/* ---------- kurulum ---------- */

async function baslat() {
  const yanıt = await fetch("/api/account").catch(() => null);
  const veri = yanıt && yanıt.ok ? await yanıt.json().catch(() => null) : null;
  if (!veri?.uyelik) {
    bölüm("#uyelikKapali", true);
    bölüm("#girisGerek", false);
    bölüm("#hesapIcerik", false);
    return;
  }
  ayarlar = { url: (veri.supabase_url || "").replace(/\/$/, ""), anonKey: veri.supabase_anon_key || "" };
  await hesap.kur();
  // Burada pencere açmak yerine giriş ekranına gidiyoruz: kullanıcı zaten
  // "giriş yapın" diyen boş bir sayfaya bakıyor, araya bir katman daha
  // koymanın anlamı yok. Dönüş adresi korunuyor.
  $("#btnGirisYap")?.addEventListener("click", () => {
    window.location.href = "giris.html?devam=hesabim.html";
  });
  $("#btnVeriIndir")?.addEventListener("click", veriIndir);
  $("#btnGecmisTemizle")?.addEventListener("click", gecmisiTemizle);
  $("#btnHesapSil")?.addEventListener("click", hesabiSil);
  if (await durumuCiz()) await gecmisiCiz();
}

baslat();
