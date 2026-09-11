from app.errors import UpstreamError


def test_health_and_index(client):
    assert client.get("/api/health").json()["status"] == "ok"
    page = client.get("/")
    assert page.status_code == 200
    assert "Değerix" in page.text


def test_usages(client):
    keys = [item["key"] for item in client.get("/api/usages").json()]
    assert keys == ["konut", "ticari", "sanayi", "bag_bahce", "zeytinlik", "tarla"]


def test_admin_lists(client):
    assert client.get("/api/provinces").json() == [{"id": 70, "name": "Muğla"}]
    assert client.get("/api/provinces/70/districts").json() == [{"id": 724, "name": "Bodrum"}]
    assert client.get("/api/districts/724/neighborhoods").json() == [{"id": 122420, "name": "Yeniköy"}]


def test_parcel_at_returns_tkgm_record_with_fixed_names(client):
    response = client.get("/api/parcels/at", params={"lat": 37.0385, "lng": 27.419})
    assert response.status_code == 200
    parcel = response.json()

    assert parcel["source"] == "tkgm"
    assert (parcel["province"], parcel["district"], parcel["neighborhood"]) == ("Muğla", "Bodrum", "Yeniköy")
    assert (parcel["ada"], parcel["parsel"]) == ("1108", "6")
    assert parcel["area_m2"] == 467.87
    assert parcel["usage"] == "konut"
    assert parcel["geometry"]["type"] == "Polygon"
    assert abs(parcel["lat"] - 37.0385) < 1e-4


def test_parcel_at_falls_back_to_address_when_no_parcel(client):
    parcel = client.get("/api/parcels/at", params={"lat": 37.2, "lng": 27.5}).json()
    assert parcel["source"] == "osm"
    assert parcel["district"] == "Bodrum"
    assert parcel["area_m2"] is None and parcel["geometry"] is None


def test_parcel_at_falls_back_when_tkgm_is_down(client, fake_tkgm):
    fake_tkgm["/parsel/37.038500/27.419000/"] = UpstreamError("TKGM kapalı")
    assert client.get("/api/parcels/at", params={"lat": 37.0385, "lng": 27.419}).json()["source"] == "osm"


def test_parcel_at_sea_returns_404_with_message(client):
    response = client.get("/api/parcels/at", params={"lat": 36.5, "lng": 27.5})
    assert response.status_code == 404
    assert "bulunamadı" in response.json()["detail"]


def test_parcel_at_rejects_points_outside_turkey(client):
    assert client.get("/api/parcels/at", params={"lat": 48.85, "lng": 2.35}).status_code == 422


def test_parcel_by_number(client):
    response = client.get("/api/parcels/122420/1108/6")
    assert response.status_code == 200
    assert response.json()["parsel"] == "6"


def test_parcel_by_number_not_found(client):
    response = client.get("/api/parcels/122420/1108/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "1108 ada 999 parsel bu mahallede bulunamadı."


def test_parcel_by_number_rejects_non_numeric(client):
    assert client.get("/api/parcels/122420/12a/6").status_code == 422


def test_admin_list_upstream_error_is_502(client, fake_tkgm):
    fake_tkgm["/idariYapi/ilListe"] = UpstreamError("TKGM parsel servisine ulaşılamadı.")
    response = client.get("/api/provinces")
    assert response.status_code == 502
    assert "ulaşılamadı" in response.json()["detail"]


ESTIMATE = {"province": "Muğla", "district": "Bodrum", "area_m2": 467.87, "usage": "konut", "lat": 37.0385, "lng": 27.419}


def test_estimate_uses_district_boundary_for_location(client):
    body = client.post("/api/estimate", json=ESTIMATE | {"province_id": 70, "district_id": 724}).json()
    location = next(f for f in body["factors"] if f["key"] == "location")
    assert location["multiplier"] > 1.0  # parsel ilçe merkezine yakın
    assert body["confidence"] == "yüksek"
    assert body["low"] < body["total"] < body["high"]


def test_estimate_resolves_district_by_name(client):
    body = client.post("/api/estimate", json=ESTIMATE).json()
    location = next(f for f in body["factors"] if f["key"] == "location")
    assert location["multiplier"] != 1.0


def test_estimate_still_works_when_tkgm_is_down(client, fake_tkgm):
    fake_tkgm["/idariYapi/ilListe"] = UpstreamError("kapalı")
    fake_tkgm["/idariYapi/ilceListe/70"] = UpstreamError("kapalı")
    response = client.post("/api/estimate", json=ESTIMATE)
    assert response.status_code == 200
    location = next(f for f in response.json()["factors"] if f["key"] == "location")
    assert location["multiplier"] == 1.0


def test_estimate_validation(client):
    assert client.post("/api/estimate", json=ESTIMATE | {"usage": "havaalanı"}).status_code == 422
    assert client.post("/api/estimate", json=ESTIMATE | {"area_m2": 0}).status_code == 422


def test_search(client):
    results = client.get("/api/search", params={"q": "Yalıkavak"}).json()
    assert results[0]["name"].startswith("Yalıkavak")
    assert client.get("/api/search", params={"q": "ab"}).status_code == 422
