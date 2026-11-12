"""Tapusor'un satılık arsa duyuruları. Sunucu anahtarları tarayıcıya gönderilmez."""
import asyncio
from collections import OrderedDict, deque
from datetime import date
import math
import os
from time import monotonic
from uuid import uuid4

import httpx
from fastapi import HTTPException

BASE = "https://www.ai.tapusor.com/public/api/v2"


def configured():
    return bool(os.getenv("TAPUSOR_CLIENT_ID") and os.getenv("TAPUSOR_CLIENT_SECRET"))


def number(row, *keys):
    for key in keys:
        try:
            value = float(row[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            return value
    return None


def day(row, *keys):
    for key in keys:
        value = row.get(key)
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10]).isoformat()
            except ValueError:
                continue
    return None


def listings(body):
    data = body.get("data")
    if isinstance(data, dict):
        data = next((data[k] for k in ("listings", "items", "announcements", "records", "results", "ilanlar") if k in data), None)
    if not isinstance(data, list):
        raise ValueError("Tanımsız liste biçimi")
    result = []
    for row in data:
        if not isinstance(row, dict) or not isinstance(row.get("listing_id"), (str, int)):
            raise ValueError("İlan kimliği eksik")
        item = dict(id=str(row["listing_id"]), first_price=number(row,"first_price","ilk_fiyat"),
                    last_price=number(row,"last_price","price","son_fiyat","fiyat"), area=number(row,"area_m2","alan_m2"),
                    first_seen=day(row,"first_seen","first_seen_at","ilk_gorulme"),
                    last_seen=day(row,"last_seen","last_seen_at","son_gorulme"))
        if not any(item[k] is not None for k in ("first_price","last_price","first_seen","last_seen","area")):
            raise ValueError("İlan alanları tanınmadı")
        lat = number(row, "lat", "latitude", "enlem")
        lng = number(row, "lng", "longitude", "boylam")
        if lat and lng and 35.5 <= lat <= 42.5 and 25.5 <= lng <= 45:
            item.update(lat=lat, lng=lng)
        result.append(item)
    return result


class Feed:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.cache = OrderedDict()
        self.calls = deque()
        self.token = ""
        self.expires = 0
        self.client = None

    async def close(self):
        if self.client:
            await self.client.aclose()
        self.__init__()

    async def access_token(self):
        if self.token and monotonic() < self.expires:
            return self.token
        response = await self.client.post("oauth/token", data={
            "grant_type": "client_credentials", "client_id": os.environ["TAPUSOR_CLIENT_ID"],
            "client_secret": os.environ["TAPUSOR_CLIENT_SECRET"]})
        response.raise_for_status()
        payload = response.json()
        token = payload["access_token"]
        if not isinstance(token, str) or not token:
            raise ValueError("Geçersiz erişim yanıtı")
        self.token = token
        self.expires = monotonic() + max(0, int(payload.get("expires_in", 900))-60)
        return token

    async def fetch(self, lat, lng, radius, days, live, page):
        if not configured():
            raise HTTPException(503, "Tapusor ilan bağlantısı henüz etkinleştirilmedi.")
        key = (round(lat, 5), round(lng, 5), radius, days, live, page)
        async with self.lock:
            now = monotonic()
            if key in self.cache and self.cache[key][0] > now:
                return self.cache[key][1]
            while self.calls and self.calls[0] <= now - 3600:
                self.calls.popleft()
            try:
                limit = int(os.getenv("TAPUSOR_REQUESTS_PER_HOUR", "60"))
            except ValueError:
                raise HTTPException(503, "Sunucu ilan sorgu sınırı geçersiz.") from None
            if len(self.calls) >= limit:
                raise HTTPException(429, "Sunucunun saatlik ilan sorgu sınırına ulaşıldı.")
            self.calls.append(now)
            if self.client is None:
                self.client = httpx.AsyncClient(base_url=BASE + "/", timeout=15)
            params = dict(lat=key[0], lng=key[1], radius_m=radius, days=days, live=int(live),
                          status=1, category=3, type="list", sort="newest", limit=20, offset=page*20)
            try:
                for attempt in range(2):
                    token = await self.access_token()
                    response = await self.client.get("listings/announcements", params=params,
                        headers={"Authorization": "Bearer " + token, "X-Request-Id": str(uuid4())})
                    if response.status_code != 401 or attempt:
                        break
                    self.token = ""
                if response.status_code == 404 and response.json().get("error", {}).get("code") == "no_data":
                    rows = []
                else:
                    response.raise_for_status()
                    rows = listings(response.json())
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 429:
                    raise HTTPException(429, "Sağlayıcının sorgu kotası doldu. Daha sonra tekrar deneyin.") from None
                if status in (401,403):
                    raise HTTPException(503, "Sağlayıcı ilan erişimini onaylamadı. Sunucu hesabı ve ilan yetkisi kontrol edilmeli.") from None
                raise HTTPException(502, "İlan sağlayıcısı sorguyu tamamlayamadı.") from None
            except httpx.RequestError:
                raise HTTPException(503, "İlan sağlayıcısına şu anda ulaşılamıyor.") from None
            except (ValueError, TypeError, KeyError, AttributeError):
                raise HTTPException(502, "Sağlayıcının ilan yanıtı okunamadı.") from None
            result = dict(items=rows, next_page=page+1 if len(rows)==20 and page<75 else None)
            self.cache[key] = (monotonic()+900, result)
            self.cache.move_to_end(key)
            if len(self.cache)>256:
                self.cache.popitem(last=False)
            return result


feed = Feed()
