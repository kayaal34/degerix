/* Açık / koyu tema anahtarı.
 *
 * Üç durum değil iki: "otomatik" (işletim sistemine uy) ve kullanıcının
 * elle seçtiği. Kullanıcı seçmediyse hiçbir şey saklanmaz ve sayfa
 * işletim sistemini izler; seçtiği an tercihi saklanır ve artık ona uyar.
 *
 * Tema bayrağının KENDİSİ burada değil, her sayfanın <head>'indeki iki
 * satırda uygulanıyor. Sebebi: bu dosya gövdenin sonunda çalışıyor, o ana
 * kadar sayfa bir kez açık temada boyanmış oluyor ve koyu tema seçmiş
 * kullanıcı her gezinmede beyaz bir çakma görüyor. Burada yalnızca düğme
 * var.
 */

const TEMA_ANAHTARI = "degerix.tema";

function oku() {
  try {
    const deger = localStorage.getItem(TEMA_ANAHTARI);
    return deger === "dark" || deger === "light" ? deger : null;
  } catch {
    return null;   // gizli sekme: tercih saklanmaz, otomatik kalır
  }
}

function yaz(deger) {
  try {
    if (deger) localStorage.setItem(TEMA_ANAHTARI, deger);
    else localStorage.removeItem(TEMA_ANAHTARI);
  } catch {
    /* saklanamadı: tema bu sayfada yine de değişir, kalıcı olmaz */
  }
}

function suAnKoyu() {
  const secilen = oku();
  if (secilen) return secilen === "dark";
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

function uygula(koyu) {
  document.documentElement.dataset.theme = koyu ? "dark" : "light";
  ciz(koyu);
  // Tarayıcı arayüzü (adres çubuğu) de temayla uyumlu olsun
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = koyu ? "#0e1512" : "#14543a";
  // Haritanın karo katmanı temadan haberdar olsun
  document.dispatchEvent(new CustomEvent("tema-degisti", { detail: { koyu } }));
}

const GUNES = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6"/></svg>';
const AY = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.2A8.2 8.2 0 0 1 9.8 4 8.4 8.4 0 1 0 20 14.2Z"/></svg>';

let dugme = null;

function ciz(koyu) {
  if (!dugme) return;
  dugme.innerHTML = koyu ? GUNES : AY;
  // Düğme ne YAPACAĞINI söyler, ne olduğunu değil: ekranda koyu tema
  // varken "koyu tema" yazan bir düğme, basınca ne olacağını saklıyor.
  const etiket = koyu ? "Açık temaya geç" : "Koyu temaya geç";
  dugme.setAttribute("aria-label", etiket);
  dugme.title = etiket;
  dugme.setAttribute("aria-pressed", String(koyu));
}

function kur() {
  dugme = document.getElementById("temaDugmesi");
  if (!dugme) return;
  ciz(suAnKoyu());
  dugme.addEventListener("click", () => {
    const koyu = !suAnKoyu();
    yaz(koyu ? "dark" : "light");
    uygula(koyu);
  });

  // Kullanıcı elle seçmediyse işletim sistemi değişince biz de değişelim
  window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", (olay) => {
    if (!oku()) uygula(olay.matches);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", kur, { once: true });
} else {
  kur();
}
