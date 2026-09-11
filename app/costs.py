"""
Yapı yaklaşık birim maliyetleri (TL/m²).

Kaynak: Çevre, Şehircilik ve İklim Değişikliği Bakanlığı, "Mimarlık ve Mühendislik
Hizmet Bedellerinin Hesabında Kullanılacak 2026 Yılı Yapı Yaklaşık Birim Maliyetleri
Hakkında Tebliğ", Resmî Gazete 3/2/2026, sayı 33157.

Rakamlara KDV dâhil değildir; %15 genel gider ve %10 yüklenici kârı dâhildir.
Arsa bedeli, çevre düzenlemesi ve bina dışı altyapı giderleri dâhil değildir.

Tebliğ her yıl ocak ayında yenilenir; güncellemek için YEAR ve tablo değerlerini
yeni tebliğe göre değiştirmek yeterlidir.
"""

from .urbanity import DENSE_CLUSTER, SUBURBAN, TOWN, URBAN_CENTRE

YEAR = 2026
SOURCE = "Çevre ve Şehircilik Bakanlığı 2026 yapı yaklaşık birim maliyetleri (RG 3/2/2026, 33157)"

# Tebliğdeki tam tablo (TL/m²)
BUILDING_COSTS: dict[str, int] = {
    "I-A": 2_600, "I-B": 3_900, "I-C": 4_200, "I-D": 4_800,
    "II-A": 8_100, "II-B": 12_500, "II-C": 15_100,
    "III-A": 19_800, "III-B": 21_050, "III-C": 23_400,
    "IV-A": 26_450, "IV-B": 33_900, "IV-C": 40_500,
    "V-A": 42_350, "V-B": 43_850, "V-C": 48_750, "V-D": 53_500, "V-E": 103_500,
}

# Sınıfların bu projede kullanılan karşılıkları
CLASS_DESCRIPTIONS: dict[str, str] = {
    "II-A": "Genel amaçlı depolar",
    "II-C": "Bağ/dağ/köy evleri ve hafif sanayi tesisleri",
    "III-A": "Apartman tipi konutlar (üç kata kadar)",
    "III-B": "Konutlar (21,50 m altı) ve müstakil konutlar",
    "III-C": "İş merkezleri ve ticari yapılar (üç kat üzeri)",
}


def construction_class(usage: str, class_code: int) -> str:
    """Kullanım türü ve yerleşim sınıfına göre tebliğdeki yapı sınıfı.

    Köyde iki katlı müstakil ev ile şehir merkezinde apartman aynı maliyete
    yapılmadığı için yerleşim sınıfı da hesaba katılır.
    """
    if usage == "ticari":
        return "III-C" if class_code == URBAN_CENTRE else "III-B"
    if usage == "sanayi":
        return "II-C"
    if class_code == URBAN_CENTRE:
        return "III-B"
    if class_code in (DENSE_CLUSTER, TOWN, SUBURBAN):
        return "III-A"
    return "II-C"  # kırsal yerleşim: köy evi


def construction_cost(usage: str, class_code: int) -> tuple[str, int]:
    """(yapı sınıfı, TL/m²)"""
    building_class = construction_class(usage, class_code)
    return building_class, BUILDING_COSTS[building_class]
