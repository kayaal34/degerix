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
    loading ??= Promise.all([api("marmara.json"), api("orhaneli-archive.json"), api("listings.json")])
      .then(([regions, auctions, offers]) => {
        catalog = regions;
        archive = auctions;
        listings = offers;
        for (const city of Object.keys(catalog.cities).sort((a, b) => a.localeCompare(b, "tr"))) {
          citySelect.add(new Option(city, city));
        }
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
    $("#cityPrice").textContent = "İl geneli konut birim fiyatı · " + integer.format(data.price) + " TL/m² (" + catalog.pricePeriod + ")";
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
    const bounds = [];
    for (const [name, data] of Object.entries(catalog.cities)) {
      if (city && name !== city) continue;
      bounds.push(data.center);
      const marker = L.marker(data.center, {title: name + " bölge analizi", icon: L.divIcon({
        className: "city-pin", html: name, iconSize: [70, 24]
      })}).addTo(layer);
      marker.on("click", () => { citySelect.value = name; render(); });
    }
    const filter = $("#archiveFilter").value;
    const rows = ["all", "auction"].includes(filter)
      ? archive.records.filter(row => !city || row.province === city) : [];
    const offers = listings.filter(row => catalog.cities[row.province] && (!city || row.province === city) && matchesFilter(row, filter));
    for (const row of rows) {
      list.append(auctionCard(row, true));
      if (!row.neighborhoodId) continue;
      const point = [row.lat, row.lng];
      bounds.push(point);
      L.circleMarker(point, {radius: 7, color: "#fff", fillColor: "#a74816", fillOpacity: 1, weight: 2})
        .addTo(layer).bindPopup(auctionCard(row, true));
    }
    for (const offer of offers) list.append(offerCard(offer));
    if (city) showCity(city);
    if (bounds.length === 1) map.setView(bounds[0], 9);
    else map.fitBounds(bounds, {padding: [32, 32], maxZoom: 10});
    $("#exploreStatus").textContent = (city || "11 il") + " · " + rows.length + " ihale kaydı · " + offers.length + " emlak ilanı";
    if (!list.childElementCount) list.append(el("p", "hint", "Bu seçim için arşiv kaydı yok."));
  }

  $("#archiveFilter").addEventListener("change", render);
  citySelect.addEventListener("change", render);
  document.addEventListener("map-tab", async event => {
    active = event.detail === "explore";
    $("#emptyState").hidden = active || Boolean(state.parcel);
    $("#result").hidden = active || !state.parcel;
    if (!active) { layer.remove(); return; }
    $("#exploreStatus").textContent = "Bölge verileri yükleniyor…";
    try {
      await loadCatalog();
      if (active) { layer.addTo(map); render(); }
    } catch { $("#exploreStatus").textContent = "Veriler alınamadı. Marmara keşfine tekrar dokunun."; }
  });
  document.addEventListener("parcel-selected", async event => {
    const parcel = event.detail;
    if (active) selectTab("map");
    const box = $("#parcelArchive");
    box.hidden = true;
    if (!parcel.neighborhood_id) return;
    try { await loadCatalog(); } catch { return; }
    if (parcel !== state.parcel) return;
    const rows = archive.records.filter(r => r.neighborhoodId === parcel.neighborhood_id &&
      String(parcel.ada) === r.ada && String(parcel.parsel) === r.parcel);
    box.replaceChildren(...rows.map(row => auctionCard(row, false)));
    box.hidden = !rows.length;
  });
  if (location.hash === "#marmara" && !new URLSearchParams(location.search).has("lat")) selectTab("explore");
})();
