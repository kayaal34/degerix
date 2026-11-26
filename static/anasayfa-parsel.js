"use strict";

(() => {
  const form = document.querySelector("#parcelQuick");
  const province = document.querySelector("#quickProvince");
  const district = document.querySelector("#quickDistrict");
  const neighborhood = document.querySelector("#quickNeighborhood");
  const submit = document.querySelector("#quickSubmit");
  const status = document.querySelector("#quickStatus");
  const sort = new Intl.Collator("tr");
  let pending;

  function reset(select, label) {
    select.replaceChildren(new Option(label, ""));
    select.disabled = true;
  }

  async function load(select, url, label) {
    pending?.abort();
    const request = new AbortController();
    pending = request;
    reset(select, "Yükleniyor…");
    status.textContent = "";
    try {
      const response = await fetch(url, { signal: request.signal });
      if (!response.ok) throw new Error("Sorgu tamamlanamadı.");
      const places = await response.json();
      if (request.signal.aborted) return;
      places.sort((a, b) => sort.compare(a.name, b.name));
      if (places.length === 0) {
        reset(select, "Kayıt bulunamadı");
        status.textContent = "Bu seçim için idari kayıt bulunamadı.";
        return;
      }
      select.replaceChildren(new Option(label, ""), ...places.map(place => new Option(place.name, place.id)));
      select.disabled = false;
    } catch {
      if (request.signal.aborted) return;
      reset(select, "Liste alınamadı");
      status.textContent = "TKGM listesi yüklenemedi. Önceki seçimi değiştirin veya Haritadan seç bağlantısını kullanın.";
    }
  }

  reset(district, "Önce il seçin");
  reset(neighborhood, "Önce ilçe seçin");
  form.hidden = false;
  load(province, "/api/provinces", "İl seçin");

  province.addEventListener("change", () => {
    pending?.abort();
    status.textContent = "";
    submit.disabled = true;
    reset(district, "Önce il seçin");
    reset(neighborhood, "Önce ilçe seçin");
    if (province.value) load(district, "/api/provinces/" + province.value + "/districts", "İlçe seçin");
  });

  district.addEventListener("change", () => {
    pending?.abort();
    status.textContent = "";
    submit.disabled = true;
    reset(neighborhood, "Önce ilçe seçin");
    if (district.value) load(neighborhood, "/api/districts/" + district.value + "/neighborhoods", "Köy veya mahalle seçin");
  });

  neighborhood.addEventListener("change", () => {
    submit.disabled = !neighborhood.value;
  });
})();
