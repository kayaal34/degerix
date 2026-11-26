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

function showMapUnavailable() {
  const message = document.createElement("p");
  message.className = "harita-hata";
  message.textContent = "Harita önizlemesi şu an yüklenemedi. Bölge keşfi bağlantısıyla devam edebilirsiniz.";
  HARITA_ALANI.replaceChildren(message);
  document.querySelector("#haritaAlt").textContent = "Türkiye bölge keşfi ayrı ekranda açılır.";
}

function exploreUrl(province) {
  return "harita.html?" + new URLSearchParams({il: province}) + "#turkiye";
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

  const names = iller.features.map(feature => feature.properties.text);
  const picker = document.querySelector("#heroMapProvince");
  picker.replaceChildren(new Option("İl seçin", ""), ...names.sort((a, b) => a.localeCompare(b, "tr")).map(name => new Option(name, name)));
  picker.addEventListener("change", () => {
    if (picker.value) window.location.href = exploreUrl(picker.value);
  });
  document.querySelector("#heroMapPicker").hidden = false;

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
        click: () => { window.location.href = exploreUrl(ad); },
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

  const legend = document.querySelector("#heroMapLegend");
  const bands = KADEMELER.map((step, index) => {
    const width = 100 / KADEMELER.length;
    return step.renk + " " + index * width + "% " + (index + 1) * width + "%";
  });
  legend.children[1].style.background = "linear-gradient(90deg," + bands.join(",") + ")";
  legend.hidden = false;
  yaziyiDoldur(fiyatlar, kayitlar.length);
}

function yaziyiDoldur(fiyatlar, kayitSayisi) {
  const alt = document.getElementById("haritaAlt");
  if (!alt) return;
  alt.textContent =
    // fiyatlar.kaynak ham seri kodunu taşıyor ("TCMB EVDS · TP.BIRIMFIYAT …").
    // Vitrine seri kodu yazmak, kullanıcıya hiçbir şey söylemeyen bir
    // mühendislik ayrıntısı; kaynağın adı yeter, kodu veri kaynakları
    // bölümünde zaten duruyor.
    `İl renkleri: ${fiyatlar.donem} konut m² fiyatı, Merkez Bankası. ` +
    (kayitSayisi ? `Turuncu noktalar: kaynağı belli ${kayitSayisi} belediye ihale ilanı.` : "");
}


if (HARITA_ALANI) {
  if (window.L) kur().catch(showMapUnavailable);
  else showMapUnavailable();
}
