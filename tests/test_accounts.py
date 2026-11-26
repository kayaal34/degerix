"""Üyelik kapısı: kota sunucuda tüketilir, hesap patlarsa hak geri verilir."""

import pytest

from app import accounts
from app.accounts import Grant, User

ISTEK = {"province": "Bursa", "area_m2": 500, "usage": "konut"}
KULLANICI = User(id="u-1", phone="+905551112233", email=None, token="jwt")


@pytest.fixture
def uyelik_acik(monkeypatch):
    """Supabase tanımlıymış gibi davran; ağa çıkılmaz."""
    monkeypatch.setattr(accounts, "configured", lambda: True)
    çağrılar: dict[str, list] = {"ac": [], "kapat": [], "iptal": []}

    async def current_user(token):
        return KULLANICI if token == "jwt" else None

    monkeypatch.setattr(accounts, "current_user", current_user)
    return çağrılar


def _hak_ver(monkeypatch, çağrılar, grant=Grant(query_id=7, source="free", status={})):
    async def open_query(user, **fields):
        çağrılar["ac"].append(fields)
        return grant

    async def close_query(user, g, unit_price, total):
        çağrılar["kapat"].append((g.query_id, unit_price, total))

    async def cancel_query(user, g):
        çağrılar["iptal"].append(g.query_id)

    monkeypatch.setattr(accounts, "open_query", open_query)
    monkeypatch.setattr(accounts, "close_query", close_query)
    monkeypatch.setattr(accounts, "cancel_query", cancel_query)


def test_uyelik_kapaliyken_kapi_yok(client):
    """Supabase tanımlı değilse uygulama üyeliksiz çalışır; kimse kapıda durmaz."""
    assert client.get("/api/account").json() == {"uyelik": False}
    assert client.post("/api/estimate", json=ISTEK).status_code == 200


def test_oturumsuz_istek_401(client, uyelik_acik):
    cevap = client.post("/api/estimate", json=ISTEK)
    assert cevap.status_code == 401
    assert cevap.json()["detail"]["kod"] == "oturum_yok"
    hesap = client.get("/api/account").json()
    assert hesap["uyelik"] is True and hesap["oturum"] is False
    # Ön yüz giriş akışını kurabilsin diye açık anahtarlar da döner
    assert {"supabase_url", "supabase_anon_key"} <= set(hesap)


def test_hak_bitince_402(client, uyelik_acik, monkeypatch):
    async def open_query(user, **fields):
        return None   # degerix_sorgu_ac izin vermedi

    monkeypatch.setattr(accounts, "open_query", open_query)
    cevap = client.post("/api/estimate", json=ISTEK, headers={"Authorization": "Bearer jwt"})
    assert cevap.status_code == 402
    assert cevap.json()["detail"]["kod"] == "hak_bitti"


def test_hak_varken_deger_doner_ve_sonuc_yazilir(client, uyelik_acik, monkeypatch):
    _hak_ver(monkeypatch, uyelik_acik)
    cevap = client.post("/api/estimate", json={**ISTEK, "district": "Mudanya", "parcel": "123/4"},
                        headers={"Authorization": "Bearer jwt"})
    assert cevap.status_code == 200
    # Hak değerlemeden önce açıldı ve sorgunun künyesi kaydedildi
    assert uyelik_acik["ac"][0]["province"] == "Bursa"
    assert uyelik_acik["ac"][0]["district"] == "Mudanya"
    assert uyelik_acik["ac"][0]["parcel"] == "123/4"
    # Sonuç aynı kayda yazıldı
    kayit_id, birim, toplam = uyelik_acik["kapat"][0]
    assert kayit_id == 7
    assert birim == cevap.json()["unit_price"]
    assert toplam == cevap.json()["total"]
    assert uyelik_acik["iptal"] == []


def test_hesap_patlarsa_hak_geri_verilir(client, uyelik_acik, monkeypatch):
    _hak_ver(monkeypatch, uyelik_acik)

    async def patlat(request):
        raise RuntimeError("TCMB yanıt vermedi")

    monkeypatch.setattr("app.main._estimate", patlat)
    with pytest.raises(RuntimeError):
        client.post("/api/estimate", json=ISTEK, headers={"Authorization": "Bearer jwt"})
    assert uyelik_acik["iptal"] == [7]      # kullanıcı rakamını alamadı, hakkı yanmadı
    assert uyelik_acik["kapat"] == []


def test_bearer_ayristirma():
    assert accounts.bearer("Bearer abc") == "abc"
    assert accounts.bearer("bearer abc") == "abc"
    assert accounts.bearer("Basic abc") is None
    assert accounts.bearer("Bearer   ") is None
    assert accounts.bearer(None) is None


def test_configured_iki_degeri_birden_ister(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    assert accounts.configured() is False
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    assert accounts.configured() is False
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    assert accounts.configured() is True


# ─────────────────────── KVKK 11. madde hakları ───────────────────────

def test_uyelik_kapaliyken_kvkk_uclari_yok(client):
    """Üyelik kurulu değilse ortada kişisel veri de yok; uçlar 404."""
    assert client.get("/api/account/data").status_code == 404
    assert client.delete("/api/account").status_code == 404


def test_verilerim_oturum_ister(client, uyelik_acik):
    assert client.get("/api/account/data").status_code == 401
    assert client.delete("/api/account").status_code == 401
    assert client.delete("/api/account/history").status_code == 401


def test_verilerim_indirilebilir_dosya_doner(client, uyelik_acik, monkeypatch):
    async def my_data(user):
        return {"hesap": {"kimlik": user.id}, "sorgular": []}

    monkeypatch.setattr(accounts, "my_data", my_data)
    cevap = client.get("/api/account/data", headers={"Authorization": "Bearer jwt"})
    assert cevap.status_code == 200
    assert cevap.json()["hesap"]["kimlik"] == "u-1"
    assert "degerix-verilerim.json" in cevap.headers["content-disposition"]


def test_hesap_silme_ve_gecmis_temizleme(client, uyelik_acik, monkeypatch):
    çağrı = []

    async def delete_account(user):
        çağrı.append(("sil", user.id))
        return {"silindi": True, "silinen_sorgu": 3}

    async def clear_history(user):
        çağrı.append(("gecmis", user.id))
        return {"silindi": True, "temizlenen": 3}

    monkeypatch.setattr(accounts, "delete_account", delete_account)
    monkeypatch.setattr(accounts, "clear_history", clear_history)

    assert client.delete("/api/account", headers={"Authorization": "Bearer jwt"}).json()["silindi"]
    assert client.delete("/api/account/history", headers={"Authorization": "Bearer jwt"}).json()["temizlenen"] == 3
    assert çağrı == [("sil", "u-1"), ("gecmis", "u-1")]
