"""
Değerix API

    uvicorn app.main:app --reload

    Arayüz  : http://localhost:8000
    Swagger : http://localhost:8000/docs
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import evds, market, nearby, nominatim, tkgm, urbanity
from .data import USAGE, CornerKey, DeedKey, IrrigationKey, RoadKey, UsageKey, UtilitiesKey, ViewKey
from .errors import NotFound, UpstreamError
from .geo import centroid_and_area
from .valuation import Comparable, Estimate, RURAL_USAGES, estimate, guess_usage

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

# .env dosyasındaki yerel ayarlar (ör. EVDS_API_KEY). Sunucuda tanımlı değişkenler ezilmez.
load_dotenv(ROOT_DIR / ".env")

# Türkiye'yi kapsayan dikdörtgen
LAT_MIN, LAT_MAX = 35.8, 42.2
LNG_MIN, LNG_MAX = 25.6, 44.9

# Çevre ölçümü için beklenecek en uzun süre; yavaş bir dış servis değeri geciktirmesin
SURROUNDINGS_BUDGET_S = 4.0


# ─────────────────────────── Şemalar ───────────────────────────

class Place(BaseModel):
    id: int
    name: str


class Parcel(BaseModel):
    source: Literal["tkgm", "osm"] = Field(
        description="tkgm: tapu kaydı bulundu · osm: parsel yok, yalnızca adres bulundu"
    )
    province: str
    district: str
    neighborhood: str | None = None
    province_id: int | None = None
    district_id: int | None = None
    neighborhood_id: int | None = None
    ada: str | None = None
    parsel: str | None = None
    area_m2: float | None = None
    nitelik: str | None = None
    usage: UsageKey = Field(description="Nitelikten tahmin edilen imar durumu")
    lat: float
    lng: float
    geometry: dict[str, Any] | None = None


class SearchResult(BaseModel):
    name: str
    lat: float
    lng: float


class UsageOption(BaseModel):
    key: UsageKey
    label: str
    zoned: bool = Field(description="İmarlı mı? İmarlıysa emsal (KAKS) sorulur")


class ComparableIn(BaseModel):
    """Kullanıcının girdiği emsal. Sunucuda saklanmaz, yalnızca hesap için kullanılır."""

    price_tl: float = Field(gt=0, le=10_000_000_000, description="Emsalin toplam fiyatı (TL)")
    area_m2: float = Field(gt=0, le=10_000_000)
    kind: Literal["ilan", "satis"] = Field(default="ilan", description="ilan: istek fiyatı · satis: gerçekleşen satış")
    label: str = Field(default="", max_length=80)


class EstimateRequest(BaseModel):
    province: str = Field(min_length=2, max_length=64, description="Parselin ili; konut fiyatı buradan alınır")
    area_m2: float = Field(gt=0, le=10_000_000)
    usage: UsageKey
    lat: float | None = Field(default=None, ge=LAT_MIN, le=LAT_MAX)
    lng: float | None = Field(default=None, ge=LNG_MIN, le=LNG_MAX)
    kaks: float | None = Field(default=None, gt=0, le=10, description="Emsal (KAKS); yalnızca imarlı arsada kullanılır")
    deed: DeedKey = Field(default="bilinmiyor", description="Tapu türü")
    share_pct: float | None = Field(default=None, gt=0, le=100, description="Hisseli tapuda kullanıcının payı (%)")
    road: RoadKey = Field(default="bilinmiyor", description="Yola cephesi var mı?")
    utilities: UtilitiesKey = Field(default="bilinmiyor", description="Elektrik ve su var mı?")
    view: ViewKey = Field(default="bilinmiyor", description="Deniz ya da göl manzarası var mı?")
    corner: CornerKey = Field(default="bilinmiyor", description="Köşe parsel mi? Yalnızca imarlı arsada kullanılır")
    irrigation: IrrigationKey = Field(default="bilinmiyor", description="Sulu mu, kuru mu? Yalnızca imarsız arazide kullanılır")
    comparables: list[ComparableIn] = Field(
        default_factory=list, max_length=10,
        description="Yakındaki emsaller; hesaba ağırlıklı olarak katılır, kaydedilmez",
    )


# ─────────────────────────── Uygulama ───────────────────────────

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await tkgm.close()
    await nominatim.close()
    await evds.close()


app = FastAPI(
    title="Değerix API",
    version="4.0.0",
    description="Haritadan ya da ada/parsel numarasıyla seçilen arsanın tahmini değerini hesaplar.",
    lifespan=lifespan,
)


@app.exception_handler(NotFound)
async def not_found_handler(_: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_: Request, exc: UpstreamError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/api/health", tags=["sistem"])
async def health() -> dict[str, Any]:
    """`stats`: bölge analizi açık mı (EVDS anahtarı tanımlı mı)."""
    return {"status": "ok", "version": app.version, "stats": evds.is_configured()}


@app.get("/api/usages", response_model=list[UsageOption], tags=["değerleme"])
async def usages() -> list[UsageOption]:
    return [
        UsageOption(key=key, label=label, zoned=key not in RURAL_USAGES)
        for key, label in USAGE.items()
    ]


# ─────────────────────────── İdari yapı ───────────────────────────

@app.get("/api/provinces", response_model=list[Place], tags=["idari yapı"])
async def provinces() -> list[dict[str, Any]]:
    return await tkgm.list_provinces()


@app.get("/api/provinces/{province_id}/districts", response_model=list[Place], tags=["idari yapı"])
async def districts(province_id: int) -> list[dict[str, Any]]:
    return await tkgm.list_districts(province_id)


@app.get("/api/districts/{district_id}/neighborhoods", response_model=list[Place], tags=["idari yapı"])
async def neighborhoods(district_id: int) -> list[dict[str, Any]]:
    return await tkgm.list_neighborhoods(district_id)


@app.get("/api/search", response_model=list[SearchResult], tags=["idari yapı"])
async def search(q: str = Query(min_length=3, max_length=120)) -> list[dict[str, Any]]:
    return await nominatim.search(q)


# ─────────────────────────── Parsel ───────────────────────────

def _text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


async def _parcel_from_feature(feature: dict[str, Any]) -> Parcel:
    props = feature["properties"]
    lat, lng, _ = centroid_and_area(feature["geometry"])
    province, district, neighborhood = await tkgm.official_names(props)
    return Parcel(
        source="tkgm",
        province=province,
        district=district,
        neighborhood=neighborhood,
        province_id=props.get("ilId"),
        district_id=props.get("ilceId"),
        neighborhood_id=props.get("mahalleId"),
        ada=_text(props.get("adaNo")),
        parsel=_text(props.get("parselNo")),
        area_m2=tkgm.parse_area(props.get("alan")),
        nitelik=props.get("nitelik") or None,
        usage=guess_usage(props.get("nitelik")),
        lat=round(lat, 6),
        lng=round(lng, 6),
        geometry=feature["geometry"],
    )


@app.get("/api/parcels/at", response_model=Parcel, tags=["parsel"])
async def parcel_at(
    lat: float = Query(ge=LAT_MIN, le=LAT_MAX),
    lng: float = Query(ge=LNG_MIN, le=LNG_MAX),
) -> Parcel:
    """Koordinattaki parsel. TKGM'de kayıt yoksa ya da servise ulaşılamazsa
    OpenStreetMap'ten yalnızca il/ilçe/mahalle bilgisi döner (alanı kullanıcı girer)."""
    try:
        return await _parcel_from_feature(await tkgm.parcel_at(lat, lng))
    except (NotFound, UpstreamError):
        pass

    place = await nominatim.reverse(lat, lng)
    if place is None:
        raise NotFound("Bu noktada parsel ya da adres bulunamadı. Kara üzerinde bir noktaya tıklayın.")
    return Parcel(source="osm", usage="konut", lat=lat, lng=lng, **place)


@app.get("/api/parcels/{neighborhood_id}/{ada}/{parsel}", response_model=Parcel, tags=["parsel"])
async def parcel_by_number(
    neighborhood_id: int,
    ada: str = PathParam(pattern=r"^\d{1,7}$"),
    parsel: str = PathParam(pattern=r"^\d{1,7}$"),
) -> Parcel:
    return await _parcel_from_feature(await tkgm.parcel_by_number(neighborhood_id, ada, parsel))


# ─────────────────────────── Değerleme ───────────────────────────

@app.post("/api/estimate", response_model=Estimate, tags=["değerleme"])
async def estimate_value(request: EstimateRequest) -> Estimate:
    """Arsanın tahmini değeri: TCMB konut fiyatı, Bakanlık inşaat maliyeti ve
    parselin yerleşim sınıfıyla hesaplanır; her adım gerekçesiyle döner."""
    housing = await market.housing_price(request.province)

    place = None
    surroundings = None
    if request.lat is not None and request.lng is not None:
        place = urbanity.describe(request.lat, request.lng)
        surroundings = await nearby.fetch_within(request.lat, request.lng, budget_s=SURROUNDINGS_BUDGET_S)

    return estimate(
        area_m2=request.area_m2,
        usage=request.usage,
        housing=housing,
        urban=place,
        surroundings=surroundings,
        kaks=request.kaks,
        deed=request.deed,
        share_pct=request.share_pct,
        road=request.road,
        utilities=request.utilities,
        view=request.view,
        corner=request.corner,
        irrigation=request.irrigation,
        comparables=[Comparable(**comparable.model_dump()) for comparable in request.comparables],
    )


# ─────────────────────────── Bölge analizi ───────────────────────────

@app.get("/api/stats/{province}", response_model=evds.ProvinceStats, tags=["bölge analizi"])
async def province_stats(province: str = PathParam(min_length=2, max_length=64)) -> evds.ProvinceStats:
    """İlin TCMB EVDS konut verileri: birim m² fiyatı, bölge konut fiyat endeksi ve satış sayısı."""
    if not evds.is_configured():
        raise HTTPException(status_code=503, detail="Bölge analizi için EVDS_API_KEY tanımlı değil.")
    return await evds.province_stats(province)


@app.middleware("http")
async def revalidate_static_files(request: Request, call_next):
    """Tarayıcı arayüz dosyalarını her açılışta doğrulasın; yeni sürümden sonra eski app.js kalmasın.

    Dosya değişmediyse ETag sayesinde 304 döner, yani yeniden indirme olmaz.
    """
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


# API rotalarından sonra bağlanmalı; aksi halde "/" her isteği yakalar
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
