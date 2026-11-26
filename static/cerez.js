/* Çerez bildirimi.
 *
 * Bilerek "kabul et / reddet" değil, yalnızca bildirim. Sitede reklam ya da
 * izleme çerezi yok; tarayıcıda tutulan her şey zorunlu veya işlevsel (oturum
 * jetonu, karşılaştırma listesi, tercihler). Zorunlu depolama için rıza
 * istemek, rıza istenmesi gereken yerlerde de anlamını boşaltır. Onay
 * düğmeleri koymak, olmayan bir izlemeyi varmış gibi göstermek olurdu.
 */

const ANAHTAR = "degerix.cerez-bildirimi";

function okundu() {
  try {
    return localStorage.getItem(ANAHTAR) === "1";
  } catch {
    return true;   // depolama yoksa her açılışta göstermek işkence olur
  }
}

function isaretle() {
  try {
    localStorage.setItem(ANAHTAR, "1");
  } catch {
    /* gizli sekme: bildirim bu oturumda kapanır, kalıcı olmaz */
  }
}

function goster() {
  const kutu = document.createElement("div");
  kutu.className = "cerez-bildirim";
  kutu.setAttribute("role", "note");

  const metin = document.createElement("p");
  metin.innerHTML = "Değerix'te reklam ve izleme çerezi yok. Tarayıcınızda yalnızca "
    + "oturumunuzu ve tercihlerinizi hatırlayan zorunlu kayıtlar tutulur. "
    + '<a href="cerez.html">Ayrıntılar</a>';

  const düğme = document.createElement("button");
  düğme.type = "button";
  düğme.className = "btn btn-ghost btn-sm";
  düğme.textContent = "Anladım";
  düğme.addEventListener("click", () => {
    isaretle();
    kutu.remove();
  });

  kutu.append(metin, düğme);
  document.body.append(kutu);
}

if (!okundu()) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", goster, { once: true });
  } else {
    goster();
  }
}
