/* Tanıtım sayfası: kaydırınca beliren bölümler.
 *
 * Üç kural:
 *  - JavaScript çalışmazsa hiçbir şey gizlenmez. Gizleme sınıfını bu dosya
 *    değil, <head>'deki satır içi betik ekliyor; böylece içerik önce görünüp
 *    sonra kaybolmuyor, betik hiç çalışmazsa da sayfa eksiksiz duruyor.
 *  - IntersectionObserver yoksa her şey anında görünür.
 *  - Hareket azaltma açıksa animasyon yok; CSS bunu kendi hallediyor.
 */

// <head>'deki güvenlik ağına "ben geldim" demek. Bu satır çalışmazsa oradaki
// vazgeçme kurulumu gizlemeyi kaldırıyor ve içerik görünür kalıyor.
window.__belirenHazir = true;

const OGELER = Array.from(document.querySelectorAll("[data-beliren]"));

function hepsiniGoster() {
  for (const oge of OGELER) oge.classList.add("belirdi");
}

if (!OGELER.length) {
  /* yapacak bir şey yok */
} else if (!("IntersectionObserver" in window)) {
  hepsiniGoster();
} else {
  // Kardeşler arasındaki sıra, sırayla belirmeleri için. Bir kerede
  // hesaplanıyor: gözlemci tetiklendiğinde DOM'a tekrar sormak gereksiz.
  const sira = new Map();
  for (const oge of OGELER) {
    const grup = oge.parentElement;
    const n = sira.get(grup) ?? 0;
    oge.style.setProperty("--sira", String(n));
    sira.set(grup, n + 1);
  }

  const gozlemci = new IntersectionObserver((kayitlar) => {
    for (const kayit of kayitlar) {
      if (!kayit.isIntersecting) continue;
      kayit.target.classList.add("belirdi");
      gozlemci.unobserve(kayit.target);   // bir kez belirir, geri kaybolmaz
    }
  }, {
    // Öge ekrana tam girmeden başlasın; alt kenardan biraz içeride tetikleniyor
    // ki kullanıcı kaydırmayı bitirdiğinde animasyon çoktan oturmuş olsun.
    rootMargin: "0px 0px -12% 0px",
    threshold: 0.08,
  });

  for (const oge of OGELER) gozlemci.observe(oge);

  // Sayfa bir çapaya (#yontem gibi) açıldıysa üstteki bölümler hiç görünmeden
  // atlanmış olabilir; gözlemci onları tetiklemez. Güvenlik ağı:
  window.addEventListener("load", () => {
    for (const oge of OGELER) {
      if (oge.getBoundingClientRect().top < 0) oge.classList.add("belirdi");
    }
  }, { once: true });
}
