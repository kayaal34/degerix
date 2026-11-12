"use strict";

(() => {
  const layer = L.layerGroup();
  const citySelect = $("#exploreCity");
  const list = $("#archiveList");
  let catalog;
  let archive;
  let listings;
  let loading;
  let active = false;

  function loadCatalog() {
    loading ??= Promise.all([api("turkiye.json"), api("orhaneli-archive.json"), api("listings.json"), api("iller.geojson")])
      .then(([regions, auctions, offers, outlines]) => {
        catalog = regions;
        archive = auctions;
        listings = offers;
        provinceShapes = outlines.features;
        const groups = [...new Set(Object.values(catalog.cities).map(city => city.group))].sort((a,b) => a.localeCompare(b,"tr"));
        for (const group of groups) regionSelect.add(new Option(group, group));
        fillCities();
      }).catch(error => {
        loading = null;
        throw error;
      });
    return loading;
  }

  function sourceLink(url, label) {
    const link = el("a", "", label);
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    return link;
  }

  const dateFormat = new Intl.DateTimeFormat("tr-TR", {dateStyle: "long", timeZone: "UTC"});

  function auctionCard(row, withAction) {
    const card = el("article", "archive-item");
    card.append(el("strong", "", row.neighborhood + " · " + row.ada + " ada / " + row.parcel + " parsel"),
      el("p", "", row.province + " / " + row.district + " · " + twoDecimals.format(row.area) + " m²"),
      el("p", "", "Muhammen bedel " + money.format(row.price) + " · " + integer.format(row.price / row.area) + " TL/m²"),
      el("p", "hint", "Belediye ihalesi · " + dateFormat.format(new Date(archive.date)) + " · Sonuç bilgisi yok"),
      sourceLink(archive.source, "İhale ilanını oku ↗"));
    if (withAction && row.neighborhoodId) {
      const button = el("button", "btn btn-ghost", "Parsel sınırını aç");
      button.type = "button";
      button.onclick = () => {
        selectTab("map");
        map.setView([row.lat, row.lng], 17);
        lookup("/api/parcels/" + [row.neighborhoodId, row.ada, row.parcel].join("/"), {fit: true});
      };
      card.append(button);
    }
    return card;
  }

  function offerCard(offer) {
    const card = el("article", "archive-item");
    card.append(el("strong", "", offer.title), el("p", "", offer.province + " / " + offer.district));
    for (const event of offer.history) {
      card.append(el("p", "", [event.date, event.status, event.price && money.format(event.price)].filter(Boolean).join(" · ")));
    }
    card.append(sourceLink(offer.url, "İlan kaynağı ↗"));
    return card;
  }

  function showCity(city) {
    const data = catalog.cities[city];
    const region = catalog.regions[data.region];
    const points = region.values.map((value, i) => ({period: catalog.periods[i], value}));
    const last = points.at(-1);
    const annual = (last.value / points.at(-13).value - 1) * 100;
    $("#cityTitle").textContent = city;
    $("#cityPrice").textContent = (data.estimated ? "Bölge ortalamasından tahmini konut birim fiyatı · " : "İl geneli konut birim fiyatı · ") + integer.format(data.price) + " TL/m² (" + catalog.pricePeriod + ")";
    $("#cityTrend").textContent = region.names.join(", ") + " · Konut fiyat endeksi, yıllık değişim " + signedPercent(annual) + " (" + last.period + ")";
    drawSparkline(points, $("#cityChart"));
    $("#cityHistory").replaceChildren(...points.reverse().flatMap(p => [el("dt", "", p.period), el("dd", "", twoDecimals.format(p.value))]));
    $("#trendSource").href = catalog.source;
    $("#cityReport").hidden = false;
  }

  function matchesFilter(offer, filter) {
    const last = offer.history.at(-1);
    if (filter === "all") return true;
    if (filter === "active") return last.status === "Aktif";
    if (filter === "removed") return last.status === "Kaldırıldı";
    if (filter !== "reduced" || last.status !== "Aktif") return false;
    const prices = offer.history.filter(event => event.price != null);
    return prices.length > 1 && prices.at(-1).price < prices.at(-2).price;
  }

  function render() {
    const city = citySelect.value;
    layer.clearLayers();
    list.replaceChildren();
    $("#cityReport").hidden = true;
    const area = selectedFeature(villages, villageSelect);
    const district = selectedFeature(districts, districtSelect);
    const inScope = row => (!regionSelect.value || catalog.cities[row.province]?.group === regionSelect.value)
      && (!city || row.province === city) && (!district || district.properties.text === row.district)
      && (!area || area.properties.id === row.neighborhoodId);
    const filter = $("#archiveFilter").value;
    const rows = ["all", "auction"].includes(filter)
      ? archive.records.filter(inScope) : [];
    const offers = listings.filter(row => catalog.cities[row.province] && inScope(row) && matchesFilter(row, filter));
    for (const row of rows) {
      list.append(auctionCard(row, true));
      if (!row.neighborhoodId) continue;
      const point = [row.lat, row.lng];

      L.circleMarker(point, {pane: "markerPane", bubblingMouseEvents: false, radius: 7, color: "#fff", fillColor: "#a74816", fillOpacity: 1, weight: 2})
        .addTo(layer).bindPopup(auctionCard(row, true));
    }
    for (const offer of offers) list.append(offerCard(offer));
    if (city) showCity(city);
    $("#exploreStatus").textContent = (city || regionSelect.value || "81 il") + " · " + rows.length + " ihale kaydı · " + offers.length + " emlak ilanı";
    if (!list.childElementCount) list.append(el("p", "hint", "Bu seçim için arşiv kaydı yok."));
  }

  $("#archiveFilter").addEventListener("change", render);
  const regionSelect = $("#exploreRegion");
  const districtSelect = $("#exploreDistrict");
  const villageSelect = $("#exploreVillage");
  const borders = L.layerGroup();
  const palette = ["#1b7460", "#83631d", "#4e66a5", "#8a5672", "#28768c", "#968443", "#805e9d"];
  let provinceShapes;
  let districts = [];
  let villages = [];
  let sequence = 0;

  function options(select, features, prompt) {
    select.replaceChildren(new Option(prompt, ""), ...features.map(f => new Option(f.properties.text, f.properties.id)));
  }

  function fillCities() {
    const cities = Object.keys(catalog.cities).filter(name => !regionSelect.value || catalog.cities[name].group === regionSelect.value);
    citySelect.replaceChildren(new Option("Tüm iller", ""), ...cities.sort((a,b) => a.localeCompare(b,"tr")).map(n => new Option(n,n)));
  }

  function selectedFeature(features, select) {
    return features.find(f => String(f.properties.id) === select.value);
  }

  let namedShapes = null;
  function labelShapes() {
    if (!active || !namedShapes) return;
    const occupied = [];
    namedShapes.eachLayer(shape => {
      if (!shape.getBounds().intersects(map.getBounds())) return;
      const bounds = shape.getBounds();
      const center = map.latLngToContainerPoint(bounds.getCenter());
      const size = map.latLngToContainerPoint(bounds.getSouthEast()).subtract(map.latLngToContainerPoint(bounds.getNorthWest()));
      const name = shape.feature.properties.text;
      const width = Math.max(42, name.length * 7);
      const box = L.bounds([center.x-width/2-3, center.y-9],[center.x+width/2+3, center.y+9]);
      const visible = size.x > width && size.y > 24 && !occupied.some(other => other.intersects(box));
      if (visible) occupied.push(box);
      const tooltip = shape.getTooltip();
      if (tooltip?.options.permanent === visible) return;
      shape.unbindTooltip();
      shape.bindTooltip(el("span", "", name), {permanent: visible, direction: visible ? "center" : "auto",
        className: visible ? "area-label" : "", sticky: !visible});
    });
  }
  map.on("zoomend moveend", labelShapes);

  function renderBorders(features, selectFeature, fit = true) {
    namedShapes = null;
    borders.clearLayers();
    const shapes = L.geoJSON(features.filter(f => f.geometry), {
      style: f => {
        const group = catalog.cities[f.properties.text]?.group || regionSelect.value;
        const index = [...regionSelect.options].findIndex(o => o.value === group);
        return {color: "#205746", weight: 1.5, fillColor: palette[(Math.max(1,index)-1) % palette.length], fillOpacity: 0.19};
      },
      onEachFeature: (f, polygon) => {
        polygon.bindTooltip(el("span", "", f.properties.text), {sticky: true});
        if (selectFeature) polygon.on("click", () => selectFeature(f));
        else polygon.on("click", event => lookupPoint(event.latlng.lat, event.latlng.lng));
      },
      bubblingMouseEvents: false
    }).addTo(borders);
    namedShapes = shapes;
    const bounds = shapes.getBounds();
    if (fit && bounds.isValid()) map.fitBounds(bounds, {padding: [18, 18],maxZoom: 16});
    labelShapes();
  }

  function showPath() {
    const city = citySelect.value;
    const district = selectedFeature(districts, districtSelect);
    const village = selectedFeature(villages, villageSelect);
    $("#mapLocation").textContent = ["Türkiye", catalog.cities[city]?.group || regionSelect.value, city, district?.properties.text, village?.properties.text].filter(Boolean).join(" › ");
    $("#mapHint").textContent = village ? "Parseli görmek için araziye dokunun" : district ? "Köy veya mahalle seçin" : city ? "İlçe seçin" : "Haritadan bir il seçin";
    $("#mapHint").hidden = false;
  }

  async function drill(level) {
    const seq = ++sequence;
    $("#retryBounds").hidden = true;
    const city = citySelect.value;
    if (level === "city") {
      districts = [];
      districtSelect.replaceChildren();
      $("#districtField").hidden = true;
    }
    villages = [];
    villageSelect.replaceChildren();
    $("#villageField").hidden = true;
    const district = selectedFeature(districts, districtSelect);
    const province = provinceShapes.find(f => f.properties.text === city);
    showPath();
    render();
    if (!province) {
      renderBorders(provinceShapes.filter(f => !regionSelect.value || catalog.cities[f.properties.text].group === regionSelect.value), f => {
        citySelect.value = f.properties.text;
        drill("city");
      });
      return;
    }
    if (level === "district" && !district) {
      drawDistricts();
      return;
    }
    const parent = district || province;
    renderBorders([parent], null);
    $("#mapHint").textContent = "TKGM sınırları yükleniyor…";
    try {
      const kind = district ? "neighborhoods" : "districts";
      const data = await api("/api/boundaries/" + kind + "/" + parent.properties.id);
      if (!active || seq !== sequence) return;
      if (district) {
        villages = data.features;
        options(villageSelect, villages, "Tüm köy ve mahalleler");
        $("#villageField").hidden = false;
        drawVillages();
      } else {
        districts = data.features;
        options(districtSelect, districts, "Tüm ilçeler");
        $("#districtField").hidden = false;
        drawDistricts();
      }
      if (!data.features.length) $("#mapHint").textContent = "Bu alan için alt sınır kaydı bulunamadı.";
    } catch {
      if (active && seq === sequence) {
        $("#mapHint").textContent = "TKGM sınırları yüklenemedi.";
        $("#retryBounds").hidden = false;
      }
    }
  }

  function drawDistricts() {
    showPath();
    renderBorders(districts, f => { districtSelect.value = String(f.properties.id); drill("district"); });
  }

  function drawVillages() {
    const village = selectedFeature(villages, villageSelect);
    showPath();
    render();
    if (village) renderBorders([village], null);
    else renderBorders(villages, f => { villageSelect.value = String(f.properties.id); drawVillages(); });
  }

  regionSelect.onchange = () => { fillCities(); drill("city"); };
  citySelect.onchange = () => drill("city");
  districtSelect.onchange = () => drill("district");
  villageSelect.onchange = drawVillages;
  $("#retryBounds").onclick = () => drill(districtSelect.value ? "district" : "city");

  document.addEventListener("map-tab", async event => {
    active = event.detail === "explore";
    $("#emptyState").hidden = active || Boolean(state.parcel);
    $("#result").hidden = active || !state.parcel;
    if (!active) {
      ++sequence;
      layer.remove(); borders.remove(); namedShapes = null;
      $("#mapHint").textContent = "Arsanın üzerine tıklayın";
      $("#mapHint").hidden = Boolean(state.parcel);
      const p = state.parcel;
      $("#mapLocation").textContent = p ? [p.province, p.district, p.neighborhood].filter(Boolean).join(" › ") : "Türkiye";
      return;
    }
    $("#exploreStatus").textContent = "Bölge verileri yükleniyor…";
    try {
      await loadCatalog();
      if (active) { borders.addTo(map); layer.addTo(map); drill("city"); }
    } catch { $("#exploreStatus").textContent = "Veriler alınamadı. Bölge keşfine tekrar dokunun."; }
  });
  const savedKey = "degerix-parsel-gecmisi-v1";
  let saved = [];
  try {
    const records = JSON.parse(localStorage.getItem(savedKey));
    if (Array.isArray(records)) saved = records.filter(r => typeof r.title === "string" && /^\d+\/\d+\/\d+$/.test(r.key));
  } catch { /* Özel taramada yalnızca bu oturumda saklanır. */ }
  let currentKey = null;

  function updateSaved() {
    const favorites = saved.filter(r => r.favorite);
    const recent = saved.filter(r => !r.favorite).slice(0, 25);
    saved = [...favorites, ...recent];
    try { localStorage.setItem(savedKey, JSON.stringify(saved)); } catch { /* Oturumda kullanılabilir. */ }
    const list = $("#savedParcelList");
    list.replaceChildren();
    for (const [name, rows] of [["Favoriler", favorites], ["Son gezilenler", recent]]) {
      if (!rows.length) continue;
      list.append(el("h4", "", name));
      for (const row of rows) {
        const button = el("button", "btn btn-ghost", row.title);
        button.type = "button";
        button.onclick = () => { selectTab("map"); lookup("/api/parcels/" + row.key, {fit:true}); };
        list.append(button);
      }
    }
    if (!saved.length) list.append(el("p", "hint", "Bir parsel açtığınızda burada görünür."));
    const favorite = favorites.some(r => r.key === currentKey);
    $("#saveParcel").textContent = favorite ? "Favorilerden çıkar" : "Favorilere ekle";
    $("#saveParcel").setAttribute("aria-pressed", String(favorite));
  }
  $("#saveParcel").onclick = () => {
    const row = saved.find(r => r.key === currentKey);
    if (row) { row.favorite = !row.favorite; updateSaved(); }
  };
  updateSaved();
  document.addEventListener("parcel-selected", async event => {
    const parcel = event.detail;
    if (active) selectTab("map");
    currentKey = parcel.neighborhood_id && parcel.ada != null && parcel.parsel != null
      ? [parcel.neighborhood_id, parcel.ada, parcel.parsel].join("/") : null;
    $("#saveParcel").hidden = !currentKey;
    if (currentKey) {
      const prior = saved.find(r => r.key === currentKey);
      saved = saved.filter(r => r.key !== currentKey);
      saved.unshift({key: currentKey, favorite: Boolean(prior?.favorite),
        title: [parcel.province, parcel.district, parcel.neighborhood, parcel.ada + "/" + parcel.parsel].filter(Boolean).join(" › ")});
      updateSaved();
    }
    const box = $("#parcelArchive");
    box.hidden = true;
    if (!parcel.neighborhood_id) return;
    try { await loadCatalog(); } catch { return; }
    if (parcel !== state.parcel) return;
    $("#mapLocation").textContent = ["Türkiye", catalog.cities[parcel.province]?.group, parcel.province, parcel.district,
      parcel.neighborhood, parcel.ada + "/" + parcel.parsel].filter(Boolean).join(" › ");
    const rows = archive.records.filter(r => r.neighborhoodId === parcel.neighborhood_id &&
      String(parcel.ada) === r.ada && String(parcel.parsel) === r.parcel);
    box.replaceChildren(...rows.map(row => auctionCard(row, false)));
    box.hidden = !rows.length;
  });
  if (location.hash !== "#ada-parsel" && !new URLSearchParams(location.search).has("lat")) selectTab("explore");
})();
