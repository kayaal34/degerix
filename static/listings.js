"use strict";

(() => {
  const panel = $("#nearbyFeed");
  const status = $("#feedStatus");
  const search = $("#feedSearch");
  const more = $("#feedNext");
  const rows = $("#feedRows");
  const day = new Intl.DateTimeFormat("tr-TR", {dateStyle: "medium", timeZone: "UTC"});
  let revision = 0;
  let nextPage = null;
  let enabled = null;
  const seen = new Set();
  const markers = L.layerGroup();

  function reset() {
    revision++;
    nextPage = null;
    seen.clear();
    markers.clearLayers();
    rows.replaceChildren();
    more.hidden = true;
    more.disabled = false;
    search.disabled = enabled === false;
    status.textContent = enabled === false ? "Tapusor bağlantısı bu sunucuda etkin değil." : "";
  }

  function card(item) {
    const box = el("article", "archive-item");
    const label = $("#feedLive").value === "true" ? "Aktif ilan" : "Yayından kalkmış ilan";
    box.append(el("strong", "", label + " · Tapusor"));
    if (item.first_seen || item.last_seen) {
      const dates = [];
      if (item.first_seen) dates.push("İlk görülme " + day.format(new Date(item.first_seen)));
      if (item.last_seen) dates.push("Son görülme " + day.format(new Date(item.last_seen)));
      box.append(el("p", "hint", dates.join(" · ")));
    }
    if (item.first_price) box.append(el("p", "", "İlk istenen fiyat " + money.format(item.first_price)));
    if (item.last_price) box.append(el("p", "", "Son istenen fiyat " + money.format(item.last_price)));
    if (item.first_price && item.last_price) {
      box.append(el("p", "", "İlk fiyata göre " + signedPercent(100 * (item.last_price / item.first_price - 1))));
    }
    if (item.area) {
      const unit = item.last_price ? " · " + money.format(item.last_price / item.area) + "/m²" : "";
      box.append(el("p", "", twoDecimals.format(item.area) + " m²" + unit));
    }
    if (item.last_price && item.last_price <= 1e10 && item.area && item.area <= 1e8) {
      const add = el("button", "btn btn-ghost");
      add.type = "button";
      const label = "Tapusor " + item.id;
      add.textContent = "Değerlemeye ilan emsali ekle";
      add.onclick = () => {
        if (state.comparables.some(c => c.label === label)) { status.textContent = "Bu ilan zaten emsallerde."; return; }
        if (state.comparables.length >= 10) { status.textContent = "En fazla 10 emsal seçilebilir."; return; }
        state.comparables.push({label, price_tl:item.last_price, area_m2:item.area, kind:"ilan"});
        saveComparables();
        renderComparables();
        runEstimate();
        status.textContent = "İlan emsallere eklendi.";
      };
      box.append(add);
    }
    return box;
  }

  async function load(page) {
    const parcel = state.parcel;
    if (!parcel || page === null) return;
    if (page === 0) reset();
    const seq = ++revision;
    search.disabled = true;
    more.disabled = true;
    status.textContent = "Tapusor ilanları sorgulanıyor…";
    const params = new URLSearchParams({lat: parcel.lat, lng: parcel.lng, radius: $("#feedRadius").value,
      days: $("#feedDays").value, live: $("#feedLive").value, page});
    try {
      const data = await api("/api/listings/nearby?" + params);
      if (seq !== revision) return;
      for (const item of data.items) {
        if (seen.has(item.id)) continue;
        rows.append(card(item));
        if (Number.isFinite(item.lat) && Number.isFinite(item.lng)) {
          const title = item.last_price ? "İlan · " + money.format(item.last_price) : "Arsa ilanı";
          L.circleMarker([item.lat, item.lng], {radius: 7, color: "#385887", fillOpacity: 0.8,
            bubblingMouseEvents: false}).bindTooltip(el("span", "", title)).addTo(markers);
        }
        seen.add(item.id);
      }
      nextPage = data.next_page;
      more.hidden = nextPage === null;
      status.textContent = seen.size ? seen.size + " ilan gösteriliyor. Fiyatlar satıcının istediği tutardır."
        : "Bu konum, dönem ve durum için sağlayıcıda ilan bulunamadı.";
    } catch (error) {
      if (seq === revision) status.textContent = error.message;
    } finally {
      if (seq === revision) { search.disabled = enabled === false; more.disabled = false; }
    }
  }

  panel.addEventListener("toggle", async () => {
    if (!panel.open) { markers.remove(); return; }
    markers.addTo(map);
    if (enabled !== null) return;
    try {
      enabled = (await api("/api/health")).listing_feed;
      if (enabled === false) reset();
    } catch { /* Sorgu düğmesi yeniden denemeye izin verir. */ }
  });
  document.addEventListener("map-tab", e => {
    if (e.detail === "explore") panel.open = false;
  });
  search.onclick = () => load(0);
  more.onclick = () => load(nextPage);
  for (const id of ["#feedLive", "#feedRadius", "#feedDays"]) $(id).onchange = reset;
  document.addEventListener("parcel-selected", () => { reset(); panel.open = false; });
})();
