"""
TCMB EVDS (Elektronik Veri Dağıtım Sistemi) istemcisi: bölge analizi için konut verileri.

evds3 servisi kullanılır; API anahtarı "key" HTTP başlığında gönderilir ve
EVDS_API_KEY ortam değişkeninden (.env) okunur. Anahtar yoksa bölge analizi
kapalıdır. Ücretsiz anahtar: https://evds3.tcmb.gov.tr

Seriler aylık ya da üç aylık yayımlandığından yanıtlar 12 saat bellekte tutulur.
"""

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from .data import fold
from .errors import NotFound, UpstreamError
from .evds_series import (
    PRICE_INDEX_PREFIX,
    PRICE_INDEX_REGIONS,
    SALES_PREFIX,
    SALES_SERIES,
    UNIT_PRICE_PREFIX,
    UNIT_PRICE_SERIES,
)

BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis"
USER_AGENT = "Degerix/3.2 (arsa degerleme portfolyo projesi)"
CACHE_TTL_S = 12 * 3600
HISTORY_MONTHS = 24

MONTHS_TR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")

_client: httpx.AsyncClient | None = None
_cache: dict[str, tuple[float, Any]] = {}


@dataclass(frozen=True)
class Point:
    period: str
    value: float


@dataclass(frozen=True)
class UnitPrice:
    value: int                  # TL/m²
    period: str
    change_pct: float | None    # geçen yılın aynı dönemine göre


@dataclass(frozen=True)
class PriceIndex:
    region: str                 # endeksin kapsadığı iller
    value: float
    period: str
    change_pct: float | None    # 12 ay öncesine göre
    history: list[Point]


@dataclass(frozen=True)
class Sales:
    last_12_months: int
    period: str                 # son ayın dönemi
    change_pct: float | None    # önceki 12 aya göre


@dataclass(frozen=True)
class ProvinceStats:
    province: str
    unit_price: UnitPrice | None
    price_index: PriceIndex | None
    sales: Sales | None


def api_key() -> str | None:
    return (os.getenv("EVDS_API_KEY") or "").strip() or None


def is_configured() -> bool:
    return api_key() is not None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def clear_cache() -> None:
    _cache.clear()


async def _fetch(path: str) -> Any:
    key = api_key()
    if key is None:
        raise UpstreamError("EVDS API anahtarı tanımlı değil.")
    try:
        # evds3 sorgu parametrelerini yol içinde bekler: /series=..&startDate=..
        response = await _get_client().get(f"{BASE_URL}/{path}", headers={"key": key})
    except httpx.HTTPError as exc:
        raise UpstreamError("TCMB EVDS servisine ulaşılamadı.") from exc
    if response.status_code in (401, 403):
        raise UpstreamError("EVDS API anahtarı geçersiz ya da yetkisiz.")
    if response.status_code != 200:
        raise UpstreamError(f"TCMB EVDS servisi hata döndürdü ({response.status_code}).")
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamError("TCMB EVDS servisinden geçersiz yanıt alındı.") from exc


async def _cached(path: str) -> Any:
    now = time.monotonic()
    hit = _cache.get(path)
    if hit is not None and hit[0] > now:
        return hit[1]
    data = await _fetch(path)
    _cache[path] = (now + CACHE_TTL_S, data)
    return data


async def fetch_series(code: str, start: date, end: date) -> list[tuple[str, float]]:
    """Seriyi eskiden yeniye (EVDS dönem etiketi, değer) çiftleri olarak döndürür; boş dönemler atlanır."""
    data = await _cached(f"series={code}&startDate={start:%d-%m-%Y}&endDate={end:%d-%m-%Y}&type=json")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise UpstreamError("TCMB EVDS servisinden beklenmeyen biçimde yanıt alındı.")

    column = code.replace(".", "_")  # yanıtta sütun adları noktasız gelir
    points = []
    for item in items:
        if not isinstance(item, dict) or item.get(column) in (None, ""):
            continue
        try:
            points.append((str(item["Tarih"]), float(item[column])))
        except (KeyError, ValueError):
            continue
    return points


def format_period(label: str) -> str:
    """EVDS dönem etiketini okunur yapar: "2026-7" → "Temmuz 2026", "2026-Q2" → "2026 2. çeyrek"."""
    year, _, part = label.partition("-")
    if part.startswith("Q"):
        return f"{year} {part[1:]}. çeyrek"
    return f"{MONTHS_TR[int(part) - 1]} {year}"


def _year_earlier(label: str) -> str:
    year, _, part = label.partition("-")
    return f"{int(year) - 1}-{part}"


def _percent_change(new: float, old: float | None) -> float | None:
    if not old:
        return None
    return round((new / old - 1) * 100, 1)


def summarize_unit_price(points: list[tuple[str, float]]) -> UnitPrice | None:
    if not points:
        return None
    label, value = points[-1]
    previous = dict(points).get(_year_earlier(label))
    return UnitPrice(value=round(value), period=format_period(label), change_pct=_percent_change(value, previous))


def summarize_price_index(region: str, points: list[tuple[str, float]]) -> PriceIndex | None:
    if not points:
        return None
    label, value = points[-1]
    previous = dict(points).get(_year_earlier(label))
    return PriceIndex(
        region=region,
        value=round(value, 2),
        period=format_period(label),
        change_pct=_percent_change(value, previous),
        history=[Point(format_period(period), round(v, 2)) for period, v in points[-(HISTORY_MONTHS + 1):]],
    )


def summarize_sales(points: list[tuple[str, float]]) -> Sales | None:
    if len(points) < 12:
        return None
    last_year = sum(value for _, value in points[-12:])
    year_before = points[-24:-12]
    previous = sum(value for _, value in year_before) if len(year_before) == 12 else None
    return Sales(
        last_12_months=round(last_year),
        period=format_period(points[-1][0]),
        change_pct=_percent_change(last_year, previous),
    )


_SALES = {fold(province): (province, code) for province, code in SALES_SERIES.items()}
_UNIT_PRICE = {fold(province): code for province, code in UNIT_PRICE_SERIES.items()}
_REGION = {fold(province): (code, members) for code, members in PRICE_INDEX_REGIONS.items() for province in members}


async def province_stats(province: str, today: date | None = None) -> ProvinceStats:
    """İlin birim m² fiyatı, bölge konut fiyat endeksi ve konut satışları.

    Bir seri alınamazsa o bölüm boş döner; hiçbiri alınamazsa hata yükseltilir.
    """
    key = fold(province)
    if key not in _SALES:
        raise NotFound(f"{province} için bölge verisi yok.")
    name, sales_code = _SALES[key]
    region_code, region_members = _REGION[key]
    unit_code = _UNIT_PRICE.get(key)

    today = today or date.today()
    start = date(today.year - 3, today.month, 1)  # 24 aylık grafik + yıllık karşılaştırma için yeterli

    async def load(code: str | None) -> list[tuple[str, float]]:
        return [] if code is None else await fetch_series(code, start, today)

    results = await asyncio.gather(
        load(f"{UNIT_PRICE_PREFIX}{unit_code}" if unit_code else None),
        load(f"{PRICE_INDEX_PREFIX}{region_code}"),
        load(f"{SALES_PREFIX}{sales_code}"),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException) and not isinstance(result, UpstreamError):
            raise result  # beklenmeyen hatalar gizlenmesin
    unit, index, sales = ([] if isinstance(result, UpstreamError) else result for result in results)

    stats = ProvinceStats(
        province=name,
        unit_price=summarize_unit_price(unit),
        price_index=summarize_price_index(", ".join(region_members), index),
        sales=summarize_sales(sales),
    )
    if stats.unit_price is None and stats.price_index is None and stats.sales is None:
        upstream = next((result for result in results if isinstance(result, UpstreamError)), None)
        raise upstream or NotFound(f"{name} için TCMB verisi bulunamadı.")
    return stats
