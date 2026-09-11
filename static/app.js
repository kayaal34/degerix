/* Değerix — harita, parsel seçimi ve değer tahmini */
"use strict";

const $ = (selector) => document.querySelector(selector);

const TURKEY = L.latLngBounds([35.8, 25.6], [42.2, 44.9]);
const MAX_AREA = 10_000_000;
const MOBILE = window.matchMedia("(max-width: 860px)");
const PARCEL_CASING = { color: "#fff", weight: 7, opacity: 0.9, fill: false };
const PARCEL_STYLE = { color: "#e8590c", weight: 3, fillColor: "#e8590c", fillOpacity: 0.18 };
const POINT_STYLE = { radius: 7, color: "#fff", weight: 2, fillColor: "#e8590c", fillOpacity: 1, interactive: false };

const money = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 });
const integer = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });
const upToOneDecimal = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1 });
const twoDecimals = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const state = {
  parcel: null,      // son seçilen parsel (API yanıtı)
  sharePoint: null,  // paylaşım bağlantısına yazılan [enlem, boylam]
  selection: null,   // haritadaki parsel poligonu ya da nokta
  pending: null,     // sorgu sürerken tıklanan noktanın işareti
  lookupSeq: 0,      // geç gelen eski yanıtların yenisini ezmesini önler
  estimateSeq: 0,
  searchSeq: 0,
};

/* ---------- Yardımcılar ---------- */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// 7,9 milyon ₺ · 264 milyon ₺ · 1,2 milyar ₺
function shortMoney(value) {
  if (value >= 1e9) return `${upToOneDecimal.format(value / 1e9)} milyar ₺`;
  if (value >= 1e6) return `${upToOneDecimal.format(value / 1e6)} milyon ₺`;
  return money.format(value);
}

async function api(path, options) {
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("Sunucuya bağlanılamadı. Bağlantınızı kontrol edip tekrar deneyin.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof body?.detail === "string" ? body.detail : "İstek işlenemedi, girilen bilgileri kontrol edin.");
  }
  return body;
}

function showAlert(message) {
  const box = $("#alert");
  box.textContent = message;
  box.hidden = false;
}

function hideAlert() {
  $("#alert").hidden = true;
}

let statusTimer;
function setMapStatus(text, tone = "loading") {
  const box = $("#mapStatus");
  clearTimeout(statusTimer);
  if (!text) {
    box.hidden = true;
    return;
  }
  box.dataset.tone = tone;
  $("#mapStatusText").textContent = text;
  box.hidden = false;
  if (tone !== "loading") statusTimer = setTimeout(() => (box.hidden = true), 4500);
}

/* ---------- Harita ---------- */

const map = L.map("map", { zoomControl: false, minZoom: 5, maxBounds: TURKEY.pad(0.2) });
map.fitBounds(TURKEY);
L.control.zoom({ position: "bottomright" }).addTo(map);

// API anahtarı gerektirmeyen altlıklar. OSM karoları düşük trafikli kullanım içindir:
// https://operations.osmfoundation.org/policies/tiles/
const streets = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> katkıcıları',
});
const satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 19,
  attribution: "Görüntü &copy; Esri, Maxar, Earthstar Geographics",
});
streets.addTo(map);
L.control.layers({ Harita: streets, Uydu: satellite }, null, { position: "topright" }).addTo(map);

map.on("click", (event) => lookupPoint(event.latlng.lat, event.latlng.lng));

function clearLayer(key) {
  if (state[key]) {
    state[key].remove();
    state[key] = null;
  }
}

function drawSelection(parcel, point, fit) {
  clearLayer("selection");
  if (parcel.geometry) {
    // Beyaz kontur, turuncu çizgiyi hem sokak haritasında hem uyduda seçilir kılar
    state.selection = L.featureGroup([
      L.geoJSON(parcel.geometry, { style: PARCEL_CASING, interactive: false }),
      L.geoJSON(parcel.geometry, { style: PARCEL_STYLE, interactive: false }),
    ]).addTo(map);
    const bounds = state.selection.getBounds();
    if (fit || !map.getBounds().contains(bounds)) map.fitBounds(bounds, { padding: [48, 48], maxZoom: 18 });
  } else {
    const latlng = point ?? [parcel.lat, parcel.lng];
    state.selection = L.circleMarker(latlng, POINT_STYLE).addTo(map);
    if (fit) map.setView(latlng, Math.max(map.getZoom(), 16));
  }
}

/* ---------- Parsel sorgusu ---------- */

async function lookup(url, { point = null, fit = false } = {}) {
  const seq = ++state.lookupSeq;
  hideAlert();
  clearLayer("pending");
  if (point) state.pending = L.circleMarker(point, POINT_STYLE).addTo(map);
  setMapStatus("Parsel sorgulanıyor…");

  try {
    const parcel = await api(url);
    if (seq !== state.lookupSeq) return;
    setMapStatus(null);
    showParcel(parcel, point, fit);
  } catch (error) {
    if (seq !== state.lookupSeq) return;
    // Haritaya tıklayan kullanıcı panele değil haritaya bakıyor
    if (point) setMapStatus(error.message, "error");
    else {
      setMapStatus(null);
      showAlert(error.message);
    }
  } finally {
    if (seq === state.lookupSeq) clearLayer("pending");
  }
}

function lookupPoint(lat, lng) {
  lookup(`/api/parcels/at?lat=${lat.toFixed(6)}&lng=${lng.toFixed(6)}`, { point: [lat, lng] });
}

function showParcel(parcel, point, fit) {
  state.parcel = parcel;
  state.sharePoint = point ?? [parcel.lat, parcel.lng];
  drawSelection(parcel, point, fit);

  const hasNumber = parcel.ada && parcel.parsel;
  $("#parcelTitle").textContent = hasNumber
    ? `${parcel.ada} ada, ${parcel.parsel} parsel`
    : parcel.neighborhood || "Seçilen konum";
  $("#parcelPlace").textContent = [hasNumber ? parcel.neighborhood : null, `${parcel.district} / ${parcel.province}`]
    .filter(Boolean)
    .join(" · ");

  const badge = $("#parcelSource");
  badge.textContent = parcel.source === "tkgm" ? "TKGM kaydı" : "Yaklaşık konum";
  badge.dataset.source = parcel.source;
  $("#parcelNote").hidden = parcel.source === "tkgm";

  const meta = [
    ["Tapu alanı", parcel.area_m2 ? `${integer.format(parcel.area_m2)} m²` : "—"],
    ["Nitelik", parcel.nitelik || "—"],
  ];
  $("#parcelMeta").replaceChildren(
    ...meta.map(([term, value]) => {
      const row = el("div");
      row.append(el("dt", "", term), el("dd", "", value));
      return row;
    }),
  );

  $("#inpArea").value = parcel.area_m2 ? Math.round(parcel.area_m2) : 500;
  $("#selUsage").value = parcel.usage;

  $("#emptyState").hidden = true;
  $("#mapHint").hidden = true;
  $("#result").hidden = false;
  updateShareUrl();
  runEstimate();

  if (MOBILE.matches) $("#result").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- Değer tahmini ---------- */

let estimateTimer;
$("#inpArea").addEventListener("input", () => {
  clearTimeout(estimateTimer);
  estimateTimer = setTimeout(runEstimate, 350);
});
$("#selUsage").addEventListener("change", runEstimate);

async function runEstimate() {
  const parcel = state.parcel;
  if (!parcel) return;

  const area = Number($("#inpArea").value);
  if (!(area > 0 && area <= MAX_AREA)) {
    renderInvalidArea();
    return;
  }

  const seq = ++state.estimateSeq;
  $("#valueCard").classList.add("is-loading");
  try {
    const result = await api("/api/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        province: parcel.province,
        district: parcel.district,
        province_id: parcel.province_id,
        district_id: parcel.district_id,
        lat: parcel.lat,
        lng: parcel.lng,
        area_m2: area,
        usage: $("#selUsage").value,
      }),
    });
    if (seq !== state.estimateSeq) return;
    hideAlert();
    renderEstimate(result, parcel);
  } catch (error) {
    if (seq === state.estimateSeq) showAlert(error.message);
  } finally {
    if (seq === state.estimateSeq) $("#valueCard").classList.remove("is-loading");
  }
}

function renderEstimate(result, parcel) {
  $("#valTotal").textContent = money.format(result.total);
  $("#valRange").textContent = `${shortMoney(result.low)} – ${shortMoney(result.high)} aralığında`;
  $("#valUnit").textContent = money.format(result.unit_price);
  const confidence = $("#valConfidence");
  confidence.textContent = `Güven: ${result.confidence}`;
  confidence.dataset.level = result.confidence;

  $("#factorList").replaceChildren(
    factorRow("İl referans fiyatı", `${parcel.province} · konut imarlı arsa`, `${money.format(result.base_price)}/m²`),
    ...result.factors.map((factor) =>
      factorRow(
        factor.label,
        factor.detail,
        `× ${twoDecimals.format(factor.multiplier)}`,
        factor.multiplier > 1.001 ? "up" : factor.multiplier < 0.999 ? "down" : "",
      ),
    ),
    factorRow("m² fiyatı", "Çarpımın yuvarlanmış sonucu", `${money.format(result.unit_price)}/m²`, "total"),
  );
}

function factorRow(title, detail, value, tone = "") {
  const row = el("li", tone === "total" ? "factor factor-total" : "factor");
  const text = el("div", "factor-text");
  text.append(el("b", "", title), el("span", "", detail));
  row.append(text, el("span", `factor-value ${tone}`.trim(), value));
  return row;
}

function renderInvalidArea() {
  state.estimateSeq++; // yoldaki isteğin sonucunu yok say
  $("#valueCard").classList.remove("is-loading");
  $("#valTotal").textContent = "—";
  $("#valRange").textContent = "Alan 1 ile 10.000.000 m² arasında olmalı";
  $("#valUnit").textContent = "—";
  $("#valConfidence").textContent = "";
  $("#factorList").replaceChildren();
}

/* ---------- Paylaşım ---------- */

function updateShareUrl() {
  const [lat, lng] = state.sharePoint;
  const url = new URL(location.href);
  url.search = new URLSearchParams({ lat: lat.toFixed(6), lng: lng.toFixed(6) }).toString();
  history.replaceState(null, "", url);
}

$("#btnShare").addEventListener("click", async () => {
  const button = $("#btnShare");
  try {
    await navigator.clipboard.writeText(location.href);
    button.textContent = "Bağlantı kopyalandı";
  } catch {
    button.textContent = "Kopyalanamadı";
  }
  setTimeout(() => (button.textContent = "Bağlantıyı kopyala"), 2000);
});

/* ---------- Sekmeler ---------- */

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => selectTab(tab.dataset.tab)));

function selectTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  $("#tab-map").hidden = name !== "map";
  $("#tab-number").hidden = name !== "number";
  if (name === "number") loadProvinces();
}

/* ---------- Ada / parsel formu ---------- */

function resetSelect(select, placeholder) {
  select.replaceChildren(new Option(placeholder, ""));
  select.disabled = true;
}

function fillSelect(select, items, placeholder) {
  select.replaceChildren(new Option(placeholder, ""), ...items.map((item) => new Option(item.name, item.id)));
  select.disabled = items.length === 0;
}

async function loadInto(select, url, placeholder, isCurrent) {
  resetSelect(select, "Yükleniyor…");
  try {
    const items = await api(url);
    if (isCurrent()) fillSelect(select, items, placeholder);
  } catch (error) {
    if (!isCurrent()) return;
    resetSelect(select, "Yüklenemedi");
    showAlert(error.message);
  }
}

let provincesRequested = false;
async function loadProvinces() {
  if (provincesRequested) return;
  provincesRequested = true;
  await loadInto($("#selProvince"), "/api/provinces", "İl seçin", () => true);
  if ($("#selProvince").disabled) provincesRequested = false; // sekmeye dönünce tekrar dene
}

$("#selProvince").addEventListener("change", () => {
  const id = $("#selProvince").value;
  resetSelect($("#selNeighborhood"), "Önce ilçe seçin");
  if (!id) return resetSelect($("#selDistrict"), "Önce il seçin");
  loadInto($("#selDistrict"), `/api/provinces/${id}/districts`, "İlçe seçin", () => $("#selProvince").value === id);
});

$("#selDistrict").addEventListener("change", () => {
  const id = $("#selDistrict").value;
  if (!id) return resetSelect($("#selNeighborhood"), "Önce ilçe seçin");
  loadInto($("#selNeighborhood"), `/api/districts/${id}/neighborhoods`, "Mahalle seçin", () => $("#selDistrict").value === id);
});

$("#numberForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const neighborhood = $("#selNeighborhood").value;
  const ada = $("#inpAda").value.trim();
  const parsel = $("#inpParsel").value.trim();
  if (!neighborhood || !/^\d+$/.test(ada) || !/^\d+$/.test(parsel)) {
    showAlert("Mahalleyi seçip ada ve parsel numarasını rakamla girin.");
    return;
  }
  lookup(`/api/parcels/${neighborhood}/${ada}/${parsel}`, { fit: true });
});

/* ---------- Yer arama ---------- */

let searchTimer;
const searchInput = $("#searchInput");

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const query = searchInput.value.trim();
  if (query.length < 3) {
    hideResults();
    return;
  }
  searchTimer = setTimeout(() => runSearch(query), 450);
});

searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideResults();
  if (event.key === "Enter") {
    event.preventDefault();
    const first = $("#searchResults button");
    if (first && !$("#searchResults").hidden) first.click();
    else if (searchInput.value.trim().length >= 3) runSearch(searchInput.value.trim());
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".search")) hideResults();
});

async function runSearch(query) {
  const seq = ++state.searchSeq;
  try {
    const places = await api(`/api/search?q=${encodeURIComponent(query)}`);
    if (seq === state.searchSeq) renderResults(places);
  } catch (error) {
    if (seq === state.searchSeq) renderResults([], error.message);
  }
}

function renderResults(places, message) {
  const list = $("#searchResults");
  if (places.length === 0) {
    list.replaceChildren(el("li", "search-empty", message || "Sonuç bulunamadı"));
  } else {
    list.replaceChildren(
      ...places.map((place) => {
        const item = el("li");
        const button = el("button", "", place.name);
        button.type = "button";
        button.addEventListener("click", () => goTo(place));
        item.append(button);
        return item;
      }),
    );
  }
  list.hidden = false;
}

function hideResults() {
  $("#searchResults").hidden = true;
}

function goTo(place) {
  hideResults();
  searchInput.value = place.name.split(",")[0];
  map.flyTo([place.lat, place.lng], 17, { duration: 1.2 });
  setMapStatus("Şimdi arsanın üzerine tıklayın", "info");
}

/* ---------- Telefon: konum ve haritaya dönüş ---------- */

$("#btnLocate").addEventListener("click", () => {
  if (!("geolocation" in navigator) || !window.isSecureContext) {
    showAlert("Konumunuzu kullanmak için güvenli (https) bağlantı ve konum desteği olan bir tarayıcı gerekir.");
    return;
  }
  setMapStatus("Konumunuz alınıyor…");
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => {
      const point = [coords.latitude, coords.longitude];
      if (!TURKEY.contains(point)) {
        setMapStatus("Konumunuz Türkiye dışında görünüyor.", "error");
        return;
      }
      map.setView(point, 18);
      lookupPoint(...point);
    },
    (error) => {
      const message = error.code === error.PERMISSION_DENIED ? "Konum izni verilmedi." : "Konumunuz alınamadı, haritadan seçin.";
      setMapStatus(message, "error");
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
  );
});

$("#btnBackToMap").addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));

/* ---------- Başlangıç ---------- */

async function init() {
  try {
    const usages = await api("/api/usages");
    $("#selUsage").replaceChildren(...usages.map((usage) => new Option(usage.label, usage.key)));
  } catch (error) {
    showAlert(error.message);
  }

  // Paylaşılan bağlantı: ?lat=..&lng=..
  const params = new URLSearchParams(location.search);
  const lat = Number.parseFloat(params.get("lat"));
  const lng = Number.parseFloat(params.get("lng"));
  if (Number.isFinite(lat) && Number.isFinite(lng) && TURKEY.contains([lat, lng])) {
    map.setView([lat, lng], 17);
    lookupPoint(lat, lng);
  }
}

init();
