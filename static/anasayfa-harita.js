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
/* Renkleri CSS'ten okuyoruz, buraya yazmıyoruz. Sabit hex yazsaydık koyu
   temada harita beyaz bir leke olarak kalırdı — nitekim ilk hâlinde öyleydi.
   Eşikler burada, renkler temada: hangisinin nerede durması gerektiği belli. */
const ESIKLER = [25000, 35000, 50000, 75000, Infinity];

function temaRengi(ad) {
  return getComputedStyle(document.documentElement).getPropertyValue(ad).trim();
}

function renk(fiyat) {
  if (!fiyat) return temaRengi("--il-0");
  const sira = ESIKLER.findIndex((esik) => fiyat <= esik);
  return temaRengi(`--il-${sira + 1}`);
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
        color: temaRengi("--il-cizgi"),
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
        mouseover: () => parca.setStyle({ weight: 2.5, color: temaRengi("--accent-bright") }),
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
      color: temaRengi("--il-cizgi"),
      weight: 1.5,
      fillColor: temaRengi("--parcel"),
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
  const lejantiCiz = () => {
    const pay = 100 / ESIKLER.length;
    const bantlar = ESIKLER.map((_, i) =>
      `${temaRengi(`--il-${i + 1}`)} ${i * pay}% ${(i + 1) * pay}%`);
    legend.children[1].style.background = `linear-gradient(90deg,${bantlar.join(",")})`;
  };
  lejantiCiz();
  legend.hidden = false;
  yaziyiDoldur(fiyatlar, kayitlar.length);

  // Tema değişince renkler yeniden okunsun. Katmanı yeniden kurmuyoruz:
  // stil fonksiyonu zaten temadan okuyor, resetStyle onu tekrar çağırıyor.
  document.addEventListener("tema-degisti", () => {
    katman.setStyle((ozellik) => ({
      fillColor: renk(fiyatlar.iller[ozellik.properties.text]),
      color: temaRengi("--il-cizgi"),
    }));
    lejantiCiz();   // lejant da aynı ölçeği göstermeli
  });
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
