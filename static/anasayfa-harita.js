/* Ana sayfadaki Türkiye haritası.
 *
 * Neden karo (tile) yok: bu bir gezinme haritası değil, tek bakışta okunan
 * bir tablo. Uydu ya da sokak karoları altına girince il renkleri okunmuyor,
 * üstelik 81 poligonun üstüne yüzlerce karo indirmek ücretsiz sunucuda ilk
 * açılışı yavaşlatıyor. Poligonlar tek dosya, karo sıfır.
 *
 * Renkler TCMB'nin il konut m² fiyatından geliyor — uydurma bir "sıcaklık"
 * değil, ölçülmüş tek bir sayı. Komşularından tahmin edilen iller taranmış
 * desenle ayrılıyor; kullanıcı ölçülmüş veriyle tahmini karıştırmasın.
 */

const HARITA_ALANI = document.getElementById("anaHarita");

if (HARITA_ALANI && window.L) {
  kur().catch((hata) => {
    // Harita süs değil ama sayfanın kalanı onsuz da çalışır: sessizce
    // düşmek yerine yerinde ne olduğunu yazıyoruz.
    HARITA_ALANI.innerHTML = "";
    const not = document.createElement("p");
    not.className = "harita-hata";
    not.textContent = "Harita şu an yüklenemedi. Haritayı aç düğmesiyle devam edebilirsiniz.";
    HARITA_ALANI.append(not);
    console.warn("Ana sayfa haritası:", hata);
  });
}

/* Fiyat → renk. Beş kademe, markanın yeşilinden açığa. Sürekli bir
   gradyan yerine kademe: okuyucu "şu il şu bantta" diyebilsin. */
const KADEMELER = [
  { ust: 25000, renk: "#e8f0ea" },
  { ust: 35000, renk: "#c3ddcd" },
  { ust: 50000, renk: "#8fbfa4" },
  { ust: 75000, renk: "#4e8f6c" },
  { ust: Infinity, renk: "#14543a" },
];

function renk(fiyat) {
  if (!fiyat) return "#eceae4";
  return KADEMELER.find((k) => fiyat <= k.ust).renk;
}

const para = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });

async function kur() {
  const [iller, fiyatlar, arsiv] = await Promise.all([
    fetch("iller.geojson").then((y) => y.json()),
    fetch("/api/housing-prices").then((y) => y.json()),
    fetch("orhaneli-archive.json").then((y) => y.json()).catch(() => ({ records: [] })),
  ]);

  const harita = L.map(HARITA_ALANI, {
    zoomControl: false,
    attributionControl: false,
    scrollWheelZoom: false,   // sayfa kaydırılırken harita yakınlaşmasın
    dragging: false,
    doubleClickZoom: false,
    touchZoom: false,
    keyboard: false,
  });

  const tahminler = new Set(fiyatlar.tahmin_edilen || []);

  const katman = L.geoJSON(iller, {
    style: (ozellik) => {
      const ad = ozellik.properties.text;
      return {
        fillColor: renk(fiyatlar.iller[ad]),
        fillOpacity: 1,
        color: "#ffffff",
        weight: 1,
        dashArray: tahminler.has(ad) ? "3 3" : null,
      };
    },
    onEachFeature: (ozellik, parca) => {
      const ad = ozellik.properties.text;
      const fiyat = fiyatlar.iller[ad];
      const tahmin = tahminler.has(ad);
      parca.bindTooltip(
        `<b>${ad}</b><br>${fiyat ? `₺${para.format(fiyat)} / m² konut` : "veri yok"}` +
        (tahmin ? "<br><i>komşularından tahmin</i>" : ""),
        { sticky: true, className: "il-ipucu" },
      );
      parca.on({
        mouseover: () => parca.setStyle({ weight: 2.5, color: "#9c7b3f" }),
        mouseout: () => katman.resetStyle(parca),
        click: () => { window.location.href = `harita.html#turkiye`; },
      });
    },
  }).addTo(harita);

  harita.fitBounds(katman.getBounds(), { padding: [8, 8] });
  harita.setMaxBounds(harita.getBounds());

  // Gerçek kayıtlar: belediye ihale ilanları. Uydurma pin yok — elimizde
  // kaynağı belli kaç kayıt varsa o kadar.
  const kayitlar = (arsiv.records || []).filter((k) => k.lat && k.lng);
  for (const kayit of kayitlar) {
    L.circleMarker([kayit.lat, kayit.lng], {
      radius: 5,
      color: "#ffffff",
      weight: 1.5,
      fillColor: "#e8590c",
      fillOpacity: 1,
    })
      .bindTooltip(
        `<b>${kayit.district} / ${kayit.province}</b><br>` +
        `${kayit.ada} ada ${kayit.parcel} parsel · ${para.format(kayit.area)} m²<br>` +
        `₺${para.format(kayit.price)} muhammen bedel`,
        { className: "il-ipucu" },
      )
      .on("click", () => {
        const p = new URLSearchParams({
          lat: kayit.lat, lng: kayit.lng, mahalle: kayit.neighborhoodId,
          ada: kayit.ada, parsel: kayit.parcel,
        });
        window.location.href = `harita.html?${p}`;
      })
      .addTo(harita);
  }

  yaziyiDoldur(fiyatlar, kayitlar.length);
}

function yaziyiDoldur(fiyatlar, kayitSayisi) {
  const alt = document.getElementById("haritaAlt");
  if (!alt) return;
  alt.textContent =
    `İl renkleri: ${fiyatlar.donem} konut m² fiyatı (${fiyatlar.kaynak}). ` +
    (kayitSayisi ? `Turuncu noktalar: kaynağı belli ${kayitSayisi} belediye ihale ilanı.` : "");
}
