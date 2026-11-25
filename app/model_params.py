"""
Değerleme modelinin ayarlanabilir katsayıları.

Buradaki değerler başlangıç varsayımıdır. tools/calibrate.py gerçek kayıtlarla
(Bursa pilot seti ve elle derlenen doğrulama verisi) katsayıları ayarlayıp
app/static_data/calibration.json dosyasına yazar; dosya varsa değerler oradan okunur.
Böylece hangi sayının varsayım, hangisinin veriyle ayarlandığı görünür kalır.

Yerleşim sınıfı kodları app/urbanity.py ile aynıdır.
"""

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .urbanity import (
    DENSE_CLUSTER,
    EMPTY,
    LOW_RURAL,
    SUBURBAN,
    TOWN,
    URBAN_CENTRE,
    VERY_LOW_RURAL,
    VILLAGE,
)

CALIBRATION_FILE = Path(__file__).resolve().parent / "static_data" / "calibration.json"


def _by_class(urban_centre: float, dense: float, town: float, suburban: float,
              village: float, low_rural: float, very_low_rural: float) -> dict[int, float]:
    return {
        URBAN_CENTRE: urban_centre,
        DENSE_CLUSTER: dense,
        TOWN: town,
        SUBURBAN: suburban,
        VILLAGE: village,
        LOW_RURAL: low_rural,
        VERY_LOW_RURAL: very_low_rural,
        EMPTY: very_low_rural,
    }


@dataclass(frozen=True)
class Parameters:
    """Modelin veriyle ayarlanabilen tüm sayıları."""

    # İl geneli konut fiyatını parselin yerleşimine indirger (il ortalaması = 1,00).
    # TCMB'nin il fiyatı ağırlıklı olarak şehir merkezini yansıttığı için kırsalda düşer.
    locality: dict[int, float] = field(default_factory=lambda: _by_class(1.05, 0.85, 0.70, 0.80, 0.50, 0.42, 0.36))

    # Emsal (KAKS) bilinmiyorsa yerleşime göre varsayılan inşaat hakkı
    default_kaks: dict[int, float] = field(default_factory=lambda: _by_class(1.50, 1.20, 0.90, 1.00, 0.50, 0.35, 0.30))

    # Geliştirme hesabı arsaya değer bırakmadığında taban: konut m² fiyatının oranı
    floor_ratio: dict[int, float] = field(default_factory=lambda: _by_class(0.100, 0.080, 0.050, 0.060, 0.030, 0.020, 0.018))

    # İmarsız arazide arsa değeri: konut m² fiyatının oranı
    farmland_ratio: dict[int, float] = field(default_factory=lambda: _by_class(0.030, 0.020, 0.015, 0.020, 0.012, 0.008, 0.006))

    # TCMB'nin konut fiyatı tüm stokun (eski + yeni) ortalamasıdır; müteahhit ise
    # yeni daire satar ve yeni konut ortalamanın üstünde fiyatlanır.
    new_build_premium: float = 1.20

    # Brüt inşaat alanının satılabilir kısmı (ortak alanlar düşülür)
    sellable_ratio: float = 0.80

    # Arsanın, yapılacak projenin hasılatından alabileceği en yüksek pay.
    # Geliştirme hesabı bir fark hesabı olduğu için pahalı piyasalarda arsaya
    # gerçekçi olmayan paylar düşebiliyor; sektörde tipik pay hasılatın %20-40'ıdır.
    max_land_share: float = 0.45

    # Müteahhidin riski ve finansman yükü; hasılatın oranı olarak düşülür.
    # Bakanlık birim maliyetleri zaten %15 genel gider ve %10 yüklenici kârı içeriyor.
    developer_margin: float = 0.15

    # Konut dışı kullanımlarda satış fiyatı farkı (konut = 1,00)
    usage_price_ratio: dict[str, float] = field(default_factory=lambda: {"konut": 1.00, "ticari": 1.25, "sanayi": 0.55})

    # İmarsız arazide kullanım farkı (tarla = 1,00)
    farmland_usage_ratio: dict[str, float] = field(default_factory=lambda: {"tarla": 1.00, "bag_bahce": 1.40, "zeytinlik": 1.60})

    # --- İmarsız parselde imar beklentisi -------------------------------------
    # 472 m²'lik bir "tarla"yı kimse ekmiyor: o parselin fiyatı tarımsal verimden
    # değil, imara açılma beklentisinden geliyor. Ölçümde imarsız arazinin birim
    # fiyatı 1 dönümün altında, 5-20 dönüm bandının 5 katı çıkıyor; tek bir
    # tarımsal oran bu farkı taşıyamaz. Bu yüzden imarsız arazi, tarımsal değer
    # ile "imarı bekleyen yapı parseli" değerinin büyüğü olarak hesaplanır.

    # İmarsız parsel, aynı yerde konut imarlı olsaydı edeceği değerin bu kadarını
    # eder; kalan fark alıcının taşıdığı imar riski ve bekleme süresidir.
    zoning_expectation: float = 0.30

    # Parselin "yapı parseli" sayıldığı büyüklük aralığı. Altında tamamen parsel
    # gibi, üstünde tamamen tarım gibi fiyatlanır; arada doğrusal geçiş.
    # Üst sınır 2.000 m² iken ölçüm bunu çürüttü: Diyarbakır/Kayapınar'da metropol
    # ilçesi içindeki 3.400 m² "tarla" piyasada 4.136 ₺/m² ederken model 513 diyordu,
    # çünkü parsel eşiğin üstünde kalıp tamamen tarımsal fiyatlanıyordu. 81 ilanda
    # sınır tarandı: 5 dönümde imarsız arazinin tipik hatası 0,88'den 0,82'ye, parsel
    # pinli kümede 1,04'ten 0,96'ya iniyor ve ortanca 1,00'da kalıyor. 10 dönüm
    # sayısal olarak biraz daha iyi görünüyor ama oraya gitmedik: 10 dönümlük parsel
    # artık gerçek bir tarladır ve veri seti bu konuda yanlı — satılığa çıkan büyük
    # imarsız parseller şehir çeperindeki spekülatif arazilere kayıyor.
    plot_area_min_m2: float = 400.0
    plot_area_max_m2: float = 5000.0

    # İmar beklentisi büyümekte olan bir yerleşim gerektirir: bu mesafeye kadar
    # tam, iki katına kadar doğrusal azalarak sıfıra iner.
    plot_settlement_km: float = 3.0

    # Beklentinin ölçütü, etkin sınıftan bu kadar basamak indirilmiş sınıfla
    # hesaplanır; 0 çevrenin yoğunluğunu olduğu gibi devralmak olurdu. Bir
    # basamak indirmek ölçülen bir seçim: 55 ilanda imarsız arazinin tipik
    # hatası (ort|log2|) 0,82'den 0,77'ye, tümünde 0,92'den 0,89'a iniyor ve
    # medyan yerinde kalıyor. Mekanizma olarak da doğrusu: imara açılacak bir
    # parsel komşu kentin bugünkü yoğunluğunu değil, bir alt kademesini alır.
    expectation_class_step: int = 1

    # --- Değer aralığı -------------------------------------------------------
    # Yöntemin kendi belirsizliği: aralığın yarı genişliğinin tabanı. Eksik
    # bilgi payları bunun üstüne eklenir.
    #
    # Bu sayılar varsayım değil, ölçüm: 42 gerçek ilana karşı hatanın yöntem
    # bazında dağılımından geliyor (tools/ilan_karsilastir.py). Daha önce taban
    # 0,08'di ve aralık 42 ilanın yalnızca 9'unu kapsıyordu; kullanıcıya
    # gösterilen güven aralığı, modelin gerçek isabetinden üç kat dardı.
    # Geliştirme hesabı en çok bilgiyi kullandığı için en dar, imarsız arazi ise
    # ne imar ne emsal bilindiğinden en geniş. Aralığı ölçülen hatanın altında
    # tutmak ürünü isabetli göstermez, yalnızca yanlış gösterir.
    basis_spread: dict[str, float] = field(default_factory=lambda: {
        "gelistirme": 0.45,   # ölçülen: 2/3 kapsama için ±%50 (n=12)
        "taban": 0.50,        # ölçülen: ±%101 ama n=4, o yüzden tamamı yazılmadı
        "arazi": 0.70,        # ölçülen: ±%76 (n=26)
        "beklenti": 0.85,     # imar beklentisi: gelir de gelmez de, en belirsiz okuma
    })

    # İlan fiyatı ile gerçekleşen satış arasındaki tipik pazarlık payı.
    # Yalnızca kalibrasyonda kullanılır: ilan fiyatları bu oranda indirilerek karşılaştırılır.
    asking_discount: float = 0.12

    # Hücrenin sınıfı ile 2 km çevresindeki en kentsel sınıfın harmanlanma ağırlığı.
    # Köyün kenarındaki parsel bomboş kırsalla aynı sayılmasın diye geçiş kademeli olur.
    nearby_class_weight: float = 0.25

    # İl merkezinin içindeki parsel: TCMB'nin il konut fiyatı zaten ağırlıklı olarak
    # bu şehirden geldiği için katsayı il ortalamasının altına düşürülmez. Küçük illerde
    # merkez, nüfus yoğunluğu düşük olduğu için ızgarada "kasaba" görünebiliyor.
    province_centre_locality: float = 1.00
    province_centre_radius_km: float = 6.0

    # Kırsalda ilçe merkezine yakınlık: merkezin dibinde en çok bu kadar prim,
    # uzaklaştıkça bu mesafede yarılanarak sönümlenir.
    rural_centre_bonus: float = 0.20
    rural_centre_decay_km: float = 10.0

    # Kullanıcının girdiği emsallerin sonuca etkisi: her emsal için ağırlık ve üst sınır.
    # Model tamamen devre dışı kalmaz; birkaç emsal yanlışsa sonucu tek başına belirlemesin.
    comparable_weight_per_record: float = 0.20
    comparable_weight_cap: float = 0.60

    # Emsal ağırlığı: emsal sayısına göre kademeli
    comparable_weight_steps: tuple[float, ...] = (0.45, 0.65, 0.80, 0.90)
    # Emsaller dağınıksa (dispersion > comparable_scatter_limit) ağırlık bu oranla çarpılır
    comparable_scatter_limit: float = 0.50
    comparable_scatter_penalty: float = 0.70
    # Medyana göre bu sınırların dışındaki emsaller elenir
    comparable_outlier_low: float = 0.25
    comparable_outlier_high: float = 4.0
    # Model ile emsal bu kattan fazla ayrışırsa uyarı verilir ve aralık genişler
    comparable_conflict_ratio: float = 3.0

    # Emsale dayanan cevabın en dar aralığı: emsaller satış değil ilan olabilir,
    # parsel farkları büyüklük düzeltmesiyle tam kapanmaz.
    comparable_min_spread: float = 0.12

    # Emsaller modelle çatıştığında aralığa eklenen pay
    comparable_conflict_spread: float = 0.15
    # Metropol yakınlığı
    metro_population_min: int = 250_000
    # Primin tamamını hak eden nüfus; aradakiler logaritmik olarak ölçeklenir.
    # Aksaray (327 bin) ile İstanbul (15,7 milyon) aynı çekimi uygulayamaz.
    metro_population_full: int = 15_000_000
    metro_bonus_max: float = 2.5
    metro_decay_km: float = 45.0
    metro_max_km: float = 150.0

    source: str = "varsayılan"


DEFAULTS = Parameters()


def _merge(defaults: Parameters, overrides: dict) -> Parameters:
    """calibration.json içindeki alanları varsayılanların üzerine yazar."""
    values = {}
    for name, current in vars(defaults).items():
        override = overrides.get(name)
        if override is None:
            values[name] = current
        elif isinstance(current, dict):
            keys_are_numbers = all(isinstance(key, int) for key in current)
            merged = dict(current)
            for key, value in override.items():
                merged[int(key) if keys_are_numbers else key] = value
            values[name] = merged
        else:
            values[name] = override
    return Parameters(**values)


@lru_cache(maxsize=1)
def load() -> Parameters:
    """Kalibrasyon dosyası varsa onunla, yoksa varsayılanlarla."""
    if not CALIBRATION_FILE.exists():
        return DEFAULTS
    data = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
    overrides = data.get("parametreler", {})
    merged = _merge(DEFAULTS, overrides)
    return Parameters(**(vars(merged) | {"source": data.get("kaynak", "kalibrasyon")}))


def reload() -> Parameters:
    """Kalibrasyon dosyası değiştiğinde önbelleği tazeler (testler ve betikler için)."""
    load.cache_clear()
    return load()
