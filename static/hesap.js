/* Üyelik: kayıt, giriş, kalan sorgu hakkı ve ödeme duvarı.
 *
 * Supabase'in JS kütüphanesi bilerek kullanılmıyor. İhtiyacımız olan üç uç var
 * (kod gönder, kodu doğrula, jetonu tazele) ve üçü de düz fetch. Böylece ne CDN
 * bağımlılığı ne de sürüm riski giriyor; projenin derlemesiz yapısı bozulmuyor.
 *
 * Üyelik sunucuda tanımlı değilse bu dosya hiçbir şey çizmez: uygulama bugünkü
 * gibi üyeliksiz çalışır.
 */

const OTURUM_ANAHTARI = "degerix.oturum";
const KOD_UZUNLUGU = 6;

const durum = {
  acik: false,        // üyelik sunucuda tanımlı mı
  url: "",
  anonKey: "",
  oturum: null,       // { access_token, refresh_token, expires_at, user_id }
  hak: null,          // /api/account yanıtı
};

const $ = (seçici) => document.querySelector(seçici);

/* ---------- oturumun saklanması ---------- */

function oturumuOku() {
  try {
    const kayıt = JSON.parse(localStorage.getItem(OTURUM_ANAHTARI));
    return kayıt?.access_token ? kayıt : null;
  } catch {
    return null;
  }
}

function oturumuYaz(oturum) {
  durum.oturum = oturum;
  try {
    if (oturum) localStorage.setItem(OTURUM_ANAHTARI, JSON.stringify(oturum));
    else localStorage.removeItem(OTURUM_ANAHTARI);
  } catch {
    /* gizli sekmede yazılamaz; oturum yalnızca bu sayfada yaşar */
  }
}

/* ---------- Supabase auth uçları ---------- */

async function auth(yol, gövde, sorgu = "") {
  const yanıt = await fetch(`${durum.url}/auth/v1/${yol}${sorgu}`, {
    method: "POST",
    headers: { apikey: durum.anonKey, "Content-Type": "application/json" },
    body: JSON.stringify(gövde),
  });
  const veri = await yanıt.json().catch(() => null);
  if (!yanıt.ok) {
    throw new Error(veri?.msg || veri?.error_description || veri?.message
      || "İşlem tamamlanamadı, birazdan tekrar deneyin.");
  }
  return veri;
}

function oturumaCevir(veri) {
  return {
    access_token: veri.access_token,
    refresh_token: veri.refresh_token,
    expires_at: veri.expires_at ?? Math.floor(Date.now() / 1000) + (veri.expires_in ?? 3600),
    user_id: veri.user?.id ?? null,
  };
}

async function tazele() {
  if (!durum.oturum?.refresh_token) return null;
  try {
    const veri = await auth("token", { refresh_token: durum.oturum.refresh_token },
      "?grant_type=refresh_token");
    oturumuYaz(oturumaCevir(veri));
    return durum.oturum;
  } catch {
    oturumuYaz(null);   // tazeleme reddedildi: oturum gerçekten bitmiş
    return null;
  }
}

/** Geçerli erişim jetonu; süresi dolmak üzereyse tazeler. */
export async function jeton() {
  if (!durum.oturum) return null;
  const kalan = (durum.oturum.expires_at ?? 0) - Math.floor(Date.now() / 1000);
  if (kalan < 60 && !(await tazele())) return null;
  return durum.oturum?.access_token ?? null;
}

/* ---------- kayıt ve giriş ---------- */

export async function kodGonder({ telefon, eposta }) {
  // Doğrulama kodu bugün e-postayla gidiyor: SMS her sağlayıcıda ücretli ve
  // hat bağlanmadan telefona kod göndermek sessizce başarısız olur. Telefon
  // yine de zorunlu alan, profile yazılıyor; hat açıldığında burası
  // { phone: telefon } ve verify'da type:"sms" olarak değişir, başka bir şey değil.
  await auth("otp", { email: eposta, create_user: true, data: { phone: telefon } });
}

export async function kodDogrula({ telefon, eposta, kod }) {
  const veri = await auth("verify", { email: eposta, token: kod, type: "email" });
  oturumuYaz(oturumaCevir(veri));
  await telefonuYaz(telefon);
  await hakYenile();
  return durum.oturum;
}

async function telefonuYaz(telefon) {
  if (!telefon || !durum.oturum?.user_id) return;
  try {
    await fetch(`${durum.url}/rest/v1/degerix_profiles?id=eq.${durum.oturum.user_id}`, {
      method: "PATCH",
      headers: {
        apikey: durum.anonKey,
        Authorization: `Bearer ${durum.oturum.access_token}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify({ phone: telefon }),
    });
  } catch {
    /* telefon kaydı giriş akışını düşürmemeli */
  }
}

export function cikis() {
  oturumuYaz(null);
  durum.hak = null;
  ciz();
}

/* ---------- hak durumu ---------- */

export async function hakYenile() {
  if (!durum.acik) return null;
  const jetonDegeri = await jeton();
  const yanıt = await fetch("/api/account", {
    headers: jetonDegeri ? { Authorization: `Bearer ${jetonDegeri}` } : {},
  }).catch(() => null);
  durum.hak = yanıt && yanıt.ok ? await yanıt.json().catch(() => null) : null;
  ciz();
  return durum.hak;
}

export function hak() {
  return durum.hak;
}

/* ---------- arayüz ---------- */

function kalanMetni() {
  const h = durum.hak;
  if (!h?.oturum) return null;
  if (h.abonelik) {
    return h.abonelik.kalan == null
      ? `${h.abonelik.plan} · sınırsız`
      : `${h.abonelik.plan} · ${h.abonelik.kalan} sorgu`;
  }
  const kalan = h.ucretsiz_kalan ?? 0;
  return kalan > 0 ? `${kalan} ücretsiz sorgu` : "Ücretsiz hak doldu";
}

function ciz() {
  const kutu = $("#hesapBar");
  if (!kutu) return;
  kutu.hidden = !durum.acik;
  if (!durum.acik) return;

  const girisli = Boolean(durum.hak?.oturum);
  $("#hesapKalan").textContent = kalanMetni() ?? "";
  $("#hesapKalan").hidden = !girisli;
  $("#hesapKimlik").textContent = durum.hak?.eposta ?? durum.hak?.telefon ?? "";
  $("#hesapKimlik").hidden = !girisli;
  $("#btnGiris").hidden = girisli;
  $("#btnCikis").hidden = !girisli;
}

function pencere(ad, acik) {
  const kutu = $(ad);
  if (kutu) kutu.hidden = !acik;
}

export function girisAc() {
  pencere("#odemePenceresi", false);
  pencere("#girisPenceresi", true);
  $("#girisHata").hidden = true;
  $("#girisTelefon")?.focus();
}

export function odemeDuvari() {
  pencere("#girisPenceresi", false);
  pencere("#odemePenceresi", true);
}

/* ---------- kurulum ---------- */

function telefonGecerli(değer) {
  // 05xx xxx xx xx ya da +905xxxxxxxxx
  const rakamlar = değer.replace(/\D/g, "");
  return /^(0?5\d{9}|905\d{9})$/.test(rakamlar);
}

function baglantilariKur() {
  $("#btnGiris")?.addEventListener("click", girisAc);
  $("#btnCikis")?.addEventListener("click", cikis);
  document.querySelectorAll("[data-kapat]").forEach((düğme) =>
    düğme.addEventListener("click", () => pencere(`#${düğme.dataset.kapat}`, false)));

  const hata = (mesaj) => {
    const kutu = $("#girisHata");
    kutu.textContent = mesaj;
    kutu.hidden = false;
  };

  $("#formKod")?.addEventListener("submit", async (olay) => {
    olay.preventDefault();
    const telefon = $("#girisTelefon").value.trim();
    const eposta = $("#girisEposta").value.trim();
    if (!telefonGecerli(telefon)) return hata("Telefon numarasını 05xx xxx xx xx biçiminde girin.");
    if (!eposta.includes("@")) return hata("Kodun gönderileceği e-postayı girin.");
    $("#girisHata").hidden = true;
    $("#btnKodGonder").disabled = true;
    try {
      await kodGonder({ telefon, eposta });
      $("#girisAdim1").hidden = true;
      $("#girisAdim2").hidden = false;
      $("#girisKodBilgi").textContent = `${eposta} adresine ${KOD_UZUNLUGU} haneli kod gönderildi.`;
      $("#girisKod").focus();
    } catch (sorun) {
      hata(sorun.message);
    } finally {
      $("#btnKodGonder").disabled = false;
    }
  });

  $("#formDogrula")?.addEventListener("submit", async (olay) => {
    olay.preventDefault();
    const kod = $("#girisKod").value.trim();
    if (kod.length < KOD_UZUNLUGU) return hata("Kodu eksiksiz girin.");
    $("#girisHata").hidden = true;
    $("#btnDogrula").disabled = true;
    try {
      await kodDogrula({
        telefon: $("#girisTelefon").value.trim(),
        eposta: $("#girisEposta").value.trim(),
        kod,
      });
      pencere("#girisPenceresi", false);
      $("#girisAdim1").hidden = false;
      $("#girisAdim2").hidden = true;
      $("#girisKod").value = "";
    } catch (sorun) {
      hata(sorun.message);
    } finally {
      $("#btnDogrula").disabled = false;
    }
  });
}

export async function kur() {
  const yanıt = await fetch("/api/account").catch(() => null);
  const veri = yanıt && yanıt.ok ? await yanıt.json().catch(() => null) : null;
  if (!veri?.uyelik) {
    ciz();                       // üyelik kapalı: çubuk gizli kalır
    return false;
  }
  durum.acik = true;
  durum.url = (veri.supabase_url || "").replace(/\/$/, "");
  durum.anonKey = veri.supabase_anon_key || "";
  durum.oturum = oturumuOku();
  baglantilariKur();
  await hakYenile();
  return true;
}
