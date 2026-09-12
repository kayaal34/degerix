"""
Arsa değer tahmini.

Model, lisanslı değerleme uzmanlarının kullandığı iki yaklaşımı resmî verilerle kurar:

  1. Geliştirme (artık değer) yöntemi — imarlı arsa:
         hasılat  = inşaat hakkı × satılabilir oran × bölgedeki konut m² fiyatı
         maliyet  = inşaat hakkı × Bakanlık yapı birim maliyeti
         arsa     = hasılat − maliyet − geliştirici payı
     Hasılat maliyeti karşılamıyorsa (köy, kırsal) değer "taban orandan" gelir:
     orada arsayı alan kişi müteahhit değil, ev yapacak kişidir.

  2. Kullanım oranı — imarsız arazi: bölgedeki konut fiyatının, kullanım türüne ve
     yerleşime bağlı oranı.

Girdiler:
    bölgedeki konut m² fiyatı → app/market.py       (TCMB EVDS, güncel)
    inşaat maliyeti           → app/costs.py        (Resmî Gazete tebliği)
    yerleşim sınıfı           → app/urbanity.py     (WorldPop + kentleşme derecesi)
    ayarlanabilir katsayılar  → app/model_params.py (kalibrasyonla güncellenir)

Saf fonksiyonlardan oluşur: ağ erişimi, veritabanı ya da rastgelelik yoktur. Aynı girdi
her zaman aynı sonucu verir ve her adım gerekçesiyle döner; arayüz hesabı adım adım
gösterebilir. "Bilmiyorum" denen sorular değeri değiştirmez ama değer aralığını
genişletir. Sonuç, satış süresine göre üç senaryo olarak da verilir.
"""

import math
import re
import statistics
from dataclasses import dataclass

from .costs import construction_cost
from .data import CORNER, DEED, IRRIGATION, ROAD, SALE_SCENARIOS, UNKNOWN, USAGE, UTILITIES, VIEW, fold
from .model_params import Parameters, load as load_parameters
from .surroundings import Surroundings, factor_rows
from .urbanity import LOW_RURAL, Urbanity, VILLAGE

RURAL_USAGES = frozenset({"tarla", "bag_bahce", "zeytinlik"})

# Sıra önemli: "Kargir Dükkan ve Arsa" ticari sayılmalı, "Kargir Ev ve Bahçe" konut.
_USAGE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("ticari", ("dukkan", "magaza", "otel", "akaryakit", "ticari", "isyeri")),
    ("sanayi", ("fabrika", "sanayi", "atolye", "imalathane")),
    ("konut", ("arsa", "bina", "ev", "konut", "kargir", "ahsap", "apartman", "mesken", "villa")),
    ("zeytinlik", ("zeytin",)),
    ("bag_bahce", ("bag", "bahce", "meyve", "findik", "narenciye")),
    ("tarla", ("tarla", "mera", "cayir", "arazi", "toprak")),
]


@dataclass(frozen=True)
class HousingPrice:
    """İl geneli konut satış fiyatı (TL/m²). app/market.py üretir."""

    province: str
    value: int
    period: str
    source: str
    live: bool          # canlı EVDS'ten mi geldi
    estimated: bool     # TCMB bu il için fiyat yayımlamıyor, bölge ortalaması kullanıldı


@dataclass(frozen=True)
class Comparable:
    """Kullanıcının girdiği emsal: yakındaki bir ilan ya da bilinen bir satış."""

    price_tl: float
    area_m2: float
    kind: str = "ilan"        # "ilan": istek fiyatı · "satis": gerçekleşen satış
    label: str = ""


@dataclass(frozen=True)
class ComparableSummary:
    """Emsallerin hesaba nasıl yansıdığı."""

    count: int
    market_unit_price: int    # emsallerin düzeltilmiş ortancası (TL/m²)
    model_unit_price: int     # emsaller hesaba katılmadan önceki değer
    weight: float             # emsallerin sonuca etkisi (0-1)
    spread_pct: float         # emsaller arasındaki dağılım


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    multiplier: float
    detail: str


@dataclass(frozen=True)
class Development:
    """Geliştirme (artık değer) hesabının ara adımları; raporda gösterilir."""

    kaks: float
    kaks_assumed: bool           # emsal girilmediği için varsayıldı mı
    buildable_m2: int            # brüt inşaat hakkı
    sellable_m2: int             # satılabilir alan
    housing_price: int           # bölgedeki konut m² satış fiyatı
    construction_class: str      # Bakanlık tebliğindeki yapı sınıfı
    construction_cost: int       # TL/m²
    revenue: int
    cost: int
    developer_share: int
    land_value: int              # artık değer (negatifse 0)
    viable: bool                 # geliştirme hesabı arsaya değer bırakıyor mu
    capped: bool = False         # arsa payı üst sınırına takıldı mı


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    timeframe: str
    value: int
    low: int
    high: int


@dataclass(frozen=True)
class Estimate:
    base_price: int              # düzeltmeler öncesi arsa m² değeri
    base_label: str
    base_detail: str
    basis: str                   # "gelistirme" · "taban" · "arazi"
    unit_price: int
    total: int
    low: int
    high: int
    confidence: str
    settlement: str              # yerleşim sınıfı etiketi
    housing: HousingPrice
    factors: list[Factor]
    scenarios: list[Scenario]
    development: Development | None = None
    comparables: ComparableSummary | None = None
    share_pct: float | None = None
    share_value: int | None = None


def blended_locality(urban: Urbanity | None, parameters: Parameters) -> float:
    """Hücrenin kentsellik katsayısını çevresiyle harmanlar.

    Kentsellik ızgarası 1 km çözünürlükte olduğu için köyün ya da kasabanın hemen
    kenarındaki parsel "boş kırsal" hücresine düşebiliyor. Çevredeki en kentsel sınıf
    daha yüksekse katsayı o yöne doğru bir miktar çekilir; böylece sınıf sınırlarında
    değer uçurumu oluşmaz.
    """
    if urban is None:
        return parameters.locality[LOW_RURAL]
    cell = parameters.locality[urban.class_code]
    nearby = parameters.locality.get(urban.nearby_class, cell)
    blended = cell if nearby <= cell else cell + (nearby - cell) * parameters.nearby_class_weight

    centre = urban.province_centre
    if centre is not None and centre.distance_km <= parameters.province_centre_radius_km:
        blended = max(blended, parameters.province_centre_locality)
    return blended


def centre_proximity(urban: Urbanity | None, parameters: Parameters) -> Factor | None:
    """Kırsalda ilçe merkezine yakınlık; şehirde zaten yerleşim sınıfı bunu içerir."""
    if urban is None or urban.class_code > VILLAGE or urban.district_centre is None:
        return None
    distance_km = urban.district_centre.distance_km
    multiplier = 1 + parameters.rural_centre_bonus * math.exp(-distance_km / parameters.rural_centre_decay_km)
    return Factor(
        "centre", "Merkeze yakınlık", round(multiplier, 3),
        f"{urban.district_centre.name} merkezine {_decimal(distance_km)} km",
    )


def adjusted_comparable_price(comparable: Comparable, area_m2: float, parameters: Parameters) -> float:
    """Emsali konu parselle karşılaştırılabilir hale getirir.

    İlan fiyatı satış fiyatı olmadığı için pazarlık payı düşülür; emsalin büyüklüğü
    farklıysa m² fiyatı büyüklük eğrisiyle konu parselin ölçeğine taşınır.
    """
    unit_price = comparable.price_tl / comparable.area_m2
    if comparable.kind == "ilan":
        unit_price *= 1 - parameters.asking_discount
    return unit_price * size_multiplier(area_m2) / size_multiplier(comparable.area_m2)


def blend_comparables(
    comparables: list[Comparable], area_m2: float, model_unit_price: float, spread: float,
    parameters: Parameters,
) -> tuple[ComparableSummary | None, float]:
    """Emsallerin ortancasını çıkarır ve değer aralığını dağılıma göre günceller."""
    prices = sorted(adjusted_comparable_price(comparable, area_m2, parameters) for comparable in comparables)
    if not prices or model_unit_price <= 0:
        return None, spread

    market_price = statistics.median(prices)
    dispersion = (prices[-1] - prices[0]) / market_price if len(prices) > 1 else 0.0
    weight = min(parameters.comparable_weight_cap, parameters.comparable_weight_per_record * len(prices))

    # Emsaller birbirini tutuyorsa aralık daralır, dağınıksa genişler
    if dispersion > 0.5:
        spread += 0.04
    elif len(prices) > 1:
        spread -= 0.03
    else:
        spread -= 0.01

    summary = ComparableSummary(
        count=len(prices),
        market_unit_price=nice_round(market_price),
        model_unit_price=nice_round(model_unit_price),
        weight=round(weight, 2),
        spread_pct=round(dispersion * 100, 1),
    )
    return summary, max(0.05, spread)


def size_multiplier(area_m2: float) -> float:
    """500 m² referans alınır; 5.000 m²'de ~0,85, 50.000 m²'de ~0,72."""
    return min(1.08, max(0.65, (area_m2 / 500) ** -0.07))


def nice_round(value: float, digits: int = 3) -> int:
    """Sahte hassasiyet vermemek için anlamlı basamağa yuvarlar (57.432.100 → 57.400.000)."""
    if value <= 0:
        return 0
    step = 10 ** max(0, math.floor(math.log10(value)) + 1 - digits)
    return int(round(value / step) * step)


def guess_usage(nitelik: str | None) -> str:
    """TKGM nitelik metninden imar durumu önerisi; kullanıcı arayüzde değiştirebilir."""
    tokens = re.findall(r"[a-z]+", fold(nitelik or ""))
    for usage, keywords in _USAGE_KEYWORDS:
        for keyword in keywords:
            if any(token == keyword or (len(keyword) >= 4 and token.startswith(keyword)) for token in tokens):
                return usage
    return "konut"


def _thousands(value: float) -> str:
    return f"{round(value):,}".replace(",", ".")


def _decimal(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def _money(value: float) -> str:
    return f"₺{_thousands(value)}"


def develop(
    *,
    area_m2: float,
    usage: str,
    class_code: int,
    local_housing_price: float,
    kaks: float | None,
    parameters: Parameters,
) -> Development:
    """İmarlı arsada geliştirme (artık değer) hesabı."""
    effective_kaks = kaks if kaks is not None else parameters.default_kaks[class_code]
    buildable = area_m2 * effective_kaks
    sellable = buildable * parameters.sellable_ratio
    sale_price = local_housing_price * parameters.usage_price_ratio.get(usage, 1.0) * parameters.new_build_premium
    revenue = sellable * sale_price

    building_class, cost_per_m2 = construction_cost(usage, class_code, local_housing_price)
    cost = buildable * cost_per_m2
    developer_share = revenue * parameters.developer_margin
    land_value = revenue - cost - developer_share

    # Geliştirme bir fark hesabıdır; pahalı piyasalarda arsaya hasılatın yarısından
    # fazlası düşebiliyor. Sektörde arsa payı tipik olarak hasılatın %20-40'ıdır.
    ceiling = revenue * parameters.max_land_share
    capped = land_value > ceiling
    land_value = min(land_value, ceiling)

    return Development(
        kaks=round(effective_kaks, 2),
        kaks_assumed=kaks is None,
        buildable_m2=round(buildable),
        sellable_m2=round(sellable),
        housing_price=round(sale_price),
        construction_class=building_class,
        construction_cost=cost_per_m2,
        revenue=round(revenue),
        cost=round(cost),
        developer_share=round(developer_share),
        land_value=max(round(land_value), 0),
        viable=land_value > 0,
        capped=capped,
    )


def estimate(
    *,
    area_m2: float,
    usage: str,
    housing: HousingPrice,
    urban: Urbanity | None = None,
    surroundings: Surroundings | None = None,
    kaks: float | None = None,
    deed: str = UNKNOWN,
    share_pct: float | None = None,
    road: str = UNKNOWN,
    utilities: str = UNKNOWN,
    view: str = UNKNOWN,
    corner: str = UNKNOWN,
    irrigation: str = UNKNOWN,
    comparables: list[Comparable] | None = None,
    parameters: Parameters | None = None,
) -> Estimate:
    if area_m2 <= 0:
        raise ValueError("Alan sıfırdan büyük olmalı.")
    if usage not in USAGE:
        raise ValueError(f"Bilinmeyen imar durumu: {usage}")
    if kaks is not None and kaks <= 0:
        raise ValueError("Emsal sıfırdan büyük olmalı.")
    if share_pct is not None and not 0 < share_pct <= 100:
        raise ValueError("Hisse payı 0 ile 100 arasında olmalı.")
    for comparable in comparables or ():
        if comparable.price_tl <= 0 or comparable.area_m2 <= 0:
            raise ValueError("Emsal fiyatı ve alanı sıfırdan büyük olmalı.")
        if comparable.kind not in ("ilan", "satis"):
            raise ValueError(f"Geçersiz emsal türü: {comparable.kind}")
    for name, answer, options in (
        ("tapu", deed, DEED), ("yol cephesi", road, ROAD), ("elektrik-su", utilities, UTILITIES),
        ("manzara", view, VIEW), ("köşe parsel", corner, CORNER), ("sulama", irrigation, IRRIGATION),
    ):
        if answer != UNKNOWN and answer not in options:
            raise ValueError(f"Geçersiz {name} yanıtı: {answer}")

    parameters = parameters or load_parameters()
    spread = 0.08  # değer aralığının yarı genişliği; her eksik bilgi büyütür
    factors: list[Factor] = []

    class_code = urban.class_code if urban is not None else LOW_RURAL
    settlement_label = urban.label if urban is not None else "yerleşim bilinmiyor"
    if urban is None:
        spread += 0.04
    if housing.estimated:
        spread += 0.05
    if not housing.live:
        spread += 0.03

    locality = blended_locality(urban, parameters)
    local_housing_price = housing.value * locality
    zoned = usage not in RURAL_USAGES
    development: Development | None = None

    if zoned:
        development = develop(
            area_m2=area_m2, usage=usage, class_code=class_code,
            local_housing_price=local_housing_price, kaks=kaks, parameters=parameters,
        )
        floor_price = local_housing_price * parameters.floor_ratio[class_code]
        development_price = development.land_value / area_m2
        if development.viable and development_price >= floor_price:
            basis = "gelistirme"
            base_price = development_price
            base_label = "Geliştirme hesabı"
            base_detail = (
                f"{_thousands(development.buildable_m2)} m² inşaat hakkı · "
                f"hasılat {_money(development.revenue)} − maliyet {_money(development.cost)} "
                f"({development.construction_class}) − geliştirici payı {_money(development.developer_share)}"
                + (f" · arsa payı hasılatın %{round(parameters.max_land_share * 100)}'i ile sınırlandı"
                   if development.capped else "")
            )
        else:
            basis = "taban"
            base_price = floor_price
            base_detail = (
                f"{settlement_label} · bölgedeki konut fiyatının "
                f"%{_decimal(parameters.floor_ratio[class_code] * 100)}'i"
            )
            base_label = "Taban değer"
            spread += 0.05
        if development.kaks_assumed:
            spread += 0.04
    else:
        basis = "arazi"
        ratio = parameters.farmland_ratio[class_code] * parameters.farmland_usage_ratio.get(usage, 1.0)
        base_price = local_housing_price * ratio
        base_label = "Arazi değeri"
        base_detail = (
            f"{USAGE[usage]} · {settlement_label} · bölgedeki konut fiyatının "
            f"%{_decimal(ratio * 100)}'i"
        )
        spread += 0.06

    if surroundings is not None:
        factors.extend(Factor(*row) for row in factor_rows(surroundings))

    proximity = centre_proximity(urban, parameters)
    if proximity is not None:
        factors.append(proximity)

    factors.append(Factor("size", "Büyüklük", round(size_multiplier(area_m2), 3), f"{_thousands(area_m2)} m² parsel"))

    utility_options = {
        key: (label, zoned_multiplier if zoned else rural_multiplier)
        for key, (label, zoned_multiplier, rural_multiplier) in UTILITIES.items()
    }
    for key, label, answer, options in (
        ("deed", "Tapu", deed, DEED),
        ("road", "Yol cephesi", road, ROAD),
        ("utilities", "Elektrik ve su", utilities, utility_options),
    ):
        if answer == UNKNOWN:
            factors.append(Factor(key, label, 1.0, "Yanıtlanmadı, aralık genişletildi"))
            spread += 0.02
        else:
            detail, multiplier = options[answer]
            factors.append(Factor(key, label, multiplier, detail))
    if deed == "hisseli":
        spread += 0.04

    # Manzara ve köşe parsel yalnızca yanıtlanınca eklenir (referans: yok / hayır)
    if view != UNKNOWN:
        detail, multiplier = VIEW[view]
        factors.append(Factor("view", "Manzara", multiplier, detail))
    if zoned and corner != UNKNOWN:
        detail, multiplier = CORNER[corner]
        factors.append(Factor("corner", "Köşe parsel", multiplier, detail))
    if not zoned:  # sulama yalnızca imarsız arazide sorulur
        if irrigation == UNKNOWN:
            factors.append(Factor("irrigation", "Sulama", 1.0, "Yanıtlanmadı, aralık genişletildi"))
            spread += 0.02
        else:
            detail, multiplier = IRRIGATION[irrigation]
            factors.append(Factor("irrigation", "Sulama", multiplier, detail))

    # Döküm yuvarlanmış başlangıç fiyatını gösterdiği için hesap da onunla yapılır
    base_price = nice_round(base_price)
    model_unit_price = base_price * math.prod(factor.multiplier for factor in factors)

    # Emsaller hesabın sonuna bir çarpan olarak girer: sonuç, modelin değeri ile
    # emsallerin ortancasının ağırlıklı geometrik ortalamasıdır.
    comparable_summary: ComparableSummary | None = None
    if comparables:
        comparable_summary, spread = blend_comparables(
            comparables, area_m2, model_unit_price, spread, parameters
        )
        if comparable_summary is not None:
            factors.append(Factor(
                "comparables", "Emsaller",
                round((comparable_summary.market_unit_price / model_unit_price) ** comparable_summary.weight, 3),
                f"{comparable_summary.count} emsalin ortancası "
                f"{_money(comparable_summary.market_unit_price)}/m² · "
                f"ağırlık %{round(comparable_summary.weight * 100)}",
            ))

    unit_price = nice_round(base_price * math.prod(factor.multiplier for factor in factors))
    total = unit_price * area_m2

    if spread <= 0.12 + 1e-9:
        confidence = "yüksek"
    elif spread <= 0.22 + 1e-9:
        confidence = "orta"
    else:
        confidence = "düşük"

    scenarios = []
    for key, label, timeframe, zoned_multiplier, rural_multiplier in SALE_SCENARIOS:
        value = total * (zoned_multiplier if zoned else rural_multiplier)
        scenarios.append(Scenario(
            key=key, label=label, timeframe=timeframe,
            value=nice_round(value),
            low=nice_round(value * (1 - spread)),
            high=nice_round(value * (1 + spread)),
        ))

    has_share = deed == "hisseli" and share_pct is not None
    return Estimate(
        base_price=nice_round(base_price),
        base_label=base_label,
        base_detail=base_detail,
        basis=basis,
        unit_price=unit_price,
        total=nice_round(total),
        low=nice_round(total * (1 - spread)),
        high=nice_round(total * (1 + spread)),
        confidence=confidence,
        settlement=settlement_label,
        housing=housing,
        factors=factors,
        scenarios=scenarios,
        development=development,
        comparables=comparable_summary,
        share_pct=share_pct if has_share else None,
        share_value=nice_round(total * share_pct / 100) if has_share else None,
    )
