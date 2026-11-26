"""
Üyelik ve sorgu hakkı: Supabase oturumunu doğrular, kotayı sunucuda tüketir.

İki kural bu dosyanın biçimini belirliyor:

1. **Kota istemciye sorulmaz.** Tarayıcı "hakkım var" diyemez; hak
   `degerix_sorgu_ac` fonksiyonuyla veritabanında atomik olarak açılır.
   Değerleme ancak o izin döndüyse hesaplanır.
2. **service_role anahtarı yoktur.** Sunucu kullanıcının kendi jetonunu
   taşır; satır güvenliği ve `auth.uid()` işi yapar. Böylece sızdığında bütün
   kullanıcıların verisini açan bir anahtar hiç var olmaz. Ortam değişkeni
   olarak yalnızca herkese açık iki değer tutulur.

Supabase tanımlı değilse uygulama **açık modda** çalışır: oturum aranmaz, kota
uygulanmaz. Portfolyo kurulumunun ve testlerin bugünkü hâli budur.
"""

import os
from dataclasses import dataclass
from typing import Any

import httpx

from .errors import UpstreamError

TIMEOUT_S = 8.0
USER_PATH = "/auth/v1/user"
RPC_PATH = "/rest/v1/rpc/"


@dataclass(frozen=True)
class User:
    id: str
    phone: str | None
    email: str | None
    token: str


@dataclass(frozen=True)
class Grant:
    """Açılmış sorgu hakkı: değerleme bittiğinde sonucu buraya yazılır."""

    query_id: int | None
    source: str
    status: dict[str, Any]


def _url() -> str | None:
    return (os.getenv("SUPABASE_URL") or "").strip().rstrip("/") or None


def _anon_key() -> str | None:
    return (os.getenv("SUPABASE_ANON_KEY") or "").strip() or None


def configured() -> bool:
    """Üyelik açık mı? İki değer de yoksa uygulama üyeliksiz çalışır."""
    return bool(_url() and _anon_key())


def bearer(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


async def current_user(token: str | None) -> User | None:
    """Jetonu Supabase'e doğrulatır. Yerel çözmek yerine sormak bilinçli:
    proje anahtarı döndüğünde ya da imza algoritması değiştiğinde sessizce
    yanlış kullanıcıya hizmet etme riski kalmıyor."""
    if not token or not configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            response = await client.get(
                f"{_url()}{USER_PATH}",
                headers={"apikey": _anon_key(), "Authorization": f"Bearer {token}"})
    except httpx.HTTPError as hata:
        raise UpstreamError("Üyelik servisine ulaşılamadı.") from hata
    if response.status_code in (401, 403):
        return None
    if response.status_code >= 400:
        raise UpstreamError("Üyelik servisi beklenmedik yanıt verdi.")
    data = response.json()
    return User(id=data["id"], phone=data.get("phone") or None,
                email=data.get("email") or None, token=token)


async def _rpc(user: User, name: str, payload: dict[str, Any]) -> Any:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            response = await client.post(
                f"{_url()}{RPC_PATH}{name}",
                headers={"apikey": _anon_key(), "Authorization": f"Bearer {user.token}",
                         "Content-Type": "application/json"},
                json=payload)
    except httpx.HTTPError as hata:
        raise UpstreamError("Üyelik servisine ulaşılamadı.") from hata
    if response.status_code >= 400:
        raise UpstreamError("Sorgu hakkı okunamadı.")
    return response.json()


async def status(user: User) -> dict[str, Any]:
    return await _rpc(user, "degerix_hak_durumu", {})


async def open_query(user: User, **fields: Any) -> Grant | None:
    """Hakkı tüketip kaydı açar. Hak bittiyse None döner."""
    result = await _rpc(user, "degerix_sorgu_ac", {
        "p_province": fields.get("province"), "p_district": fields.get("district"),
        "p_lat": fields.get("lat"), "p_lng": fields.get("lng"),
        "p_area": fields.get("area_m2"), "p_usage": fields.get("usage"),
        "p_parcel": fields.get("parcel")})
    if not result or not result.get("izin"):
        return None
    return Grant(query_id=result.get("sorgu_id"), source=result.get("kaynak", "free"),
                 status=result.get("durum") or {})


async def close_query(user: User, grant: Grant, unit_price: float, total: float) -> None:
    """Sonucu kaydeder. Burada bir hata değerlemeyi düşürmemeli: kullanıcı
    rakamını aldı, kayıt tutmak bizim işimiz."""
    if grant.query_id is None:
        return
    try:
        await _rpc(user, "degerix_sorgu_sonuc", {
            "p_id": grant.query_id, "p_unit_price": unit_price, "p_total": total})
    except UpstreamError:
        pass


async def cancel_query(user: User, grant: Grant) -> None:
    """Değerleme tamamlanamadıysa hak yanmaz."""
    if grant.query_id is None:
        return
    try:
        await _rpc(user, "degerix_sorgu_iptal", {"p_id": grant.query_id})
    except UpstreamError:
        pass
