"""
Değerleme modelinin referans verileri.

Buradaki m² fiyatları ve katsayılar gerçek piyasa verisi DEĞİLDİR; modelin nasıl
çalıştığını göstermek için seçilmiş örnek değerlerdir. Gerçek bir kaynak (ilan
verisi, tapu satış istatistikleri vb.) bağlandığında yalnızca bu dosyanın
güncellenmesi yeterlidir.
"""

from typing import Literal

# İl geneli, konut imarlı arsa için referans m² fiyatı (TL)
PROVINCE_BASE_PRICE: dict[str, int] = {
    "Adana": 3600, "Adıyaman": 1350, "Afyonkarahisar": 1900, "Ağrı": 1050,
    "Aksaray": 1650, "Amasya": 1600, "Ankara": 6200, "Antalya": 8600,
    "Ardahan": 1050, "Artvin": 1850, "Aydın": 4700, "Balıkesir": 4100,
    "Bartın": 2050, "Batman": 1500, "Bayburt": 1150, "Bilecik": 1800,
    "Bingöl": 1200, "Bitlis": 1150, "Bolu": 2900, "Burdur": 1750,
    "Bursa": 5600, "Çanakkale": 3700, "Çankırı": 1300, "Çorum": 1550,
    "Denizli": 3200, "Diyarbakır": 1900, "Düzce": 2700, "Edirne": 2450,
    "Elazığ": 1800, "Erzincan": 1500, "Erzurum": 1600, "Eskişehir": 3300,
    "Gaziantep": 2800, "Giresun": 2250, "Gümüşhane": 1250, "Hakkari": 1150,
    "Hatay": 2400, "Iğdır": 1200, "Isparta": 2100, "İstanbul": 13500,
    "İzmir": 8200, "Kahramanmaraş": 2000, "Karabük": 1750, "Karaman": 1600,
    "Kars": 1100, "Kastamonu": 1700, "Kayseri": 2700, "Kilis": 1400,
    "Kırıkkale": 1450, "Kırklareli": 2300, "Kırşehir": 1500, "Kocaeli": 5800,
    "Konya": 2500, "Kütahya": 1700, "Malatya": 1950, "Manisa": 2750,
    "Mardin": 1550, "Mersin": 4500, "Muğla": 8800, "Muş": 1100,
    "Nevşehir": 2000, "Niğde": 1550, "Ordu": 2650, "Osmaniye": 1700,
    "Rize": 3200, "Sakarya": 3900, "Samsun": 3000, "Siirt": 1250,
    "Sinop": 2300, "Sivas": 1550, "Şanlıurfa": 1800, "Şırnak": 1200,
    "Tekirdağ": 4200, "Tokat": 1450, "Trabzon": 3700, "Tunceli": 1250,
    "Uşak": 1850, "Van": 1650, "Yalova": 4800, "Yozgat": 1350,
    "Zonguldak": 2200,
}

# Listede olmayan bir il adı gelirse kullanılır
DEFAULT_BASE_PRICE = 1500

# Öne çıkan ilçeler için bölge katsayısı (1.0 = il ortalaması)
DISTRICT_FACTOR: dict[str, dict[str, float]] = {
    "İstanbul": {
        "Beşiktaş": 2.0, "Sarıyer": 1.9, "Kadıköy": 1.85, "Şişli": 1.7,
        "Bakırköy": 1.6, "Beyoğlu": 1.5, "Üsküdar": 1.5, "Ataşehir": 1.45,
        "Beykoz": 1.45, "Maltepe": 1.28, "Başakşehir": 1.24, "Beylikdüzü": 1.2,
        "Çekmeköy": 1.14, "Kartal": 1.1, "Pendik": 1.07, "Şile": 1.07,
        "Tuzla": 1.04, "Silivri": 0.93, "Esenyurt": 0.89, "Arnavutköy": 0.85,
        "Sultanbeyli": 0.81, "Çatalca": 0.77,
    },
    "Ankara": {
        "Çankaya": 1.7, "Yenimahalle": 1.27, "Gölbaşı": 1.2, "Etimesgut": 1.14,
        "Keçiören": 1.07, "Sincan": 0.89,
    },
    "İzmir": {
        "Çeşme": 2.1, "Urla": 1.76, "Karşıyaka": 1.53, "Seferihisar": 1.46,
        "Konak": 1.4, "Bornova": 1.34,
    },
    "Muğla": {
        "Bodrum": 2.3, "Marmaris": 1.88, "Fethiye": 1.76, "Datça": 1.65,
        "Milas": 1.27,
    },
    "Antalya": {
        "Kaş": 1.82, "Kemer": 1.7, "Konyaaltı": 1.65, "Muratpaşa": 1.59,
        "Alanya": 1.53, "Manavgat": 1.34,
    },
    "Bursa": {"Nilüfer": 1.46, "Mudanya": 1.4, "Osmangazi": 1.14},
    "Kocaeli": {"Gebze": 1.27, "Çayırova": 1.2, "İzmit": 1.14, "Kartepe": 1.07},
    "Sakarya": {"Sapanca": 1.59},
    "Aydın": {"Kuşadası": 1.7, "Didim": 1.4},
    "Balıkesir": {"Ayvalık": 1.65},
    "Trabzon": {"Ortahisar": 1.27, "Akçaabat": 1.14},
}

UsageKey = Literal["konut", "ticari", "sanayi", "bag_bahce", "zeytinlik", "tarla"]

# Kullanım türü → (etiket, katsayı). Referans fiyatlar konut imarlı arsaya göredir.
USAGE: dict[str, tuple[str, float]] = {
    "konut": ("Konut imarlı arsa", 1.00),
    "ticari": ("Ticari imarlı arsa", 1.45),
    "sanayi": ("Sanayi imarlı arsa", 0.80),
    "bag_bahce": ("Bağ / bahçe", 0.32),
    "zeytinlik": ("Zeytinlik", 0.36),
    "tarla": ("Tarla", 0.22),
}


_FOLD_TABLE = str.maketrans({
    "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c",
    "Â": "a", "â": "a", "Î": "i", "î": "i", "Û": "u", "û": "u",
})


def fold(text: str) -> str:
    """Türkçe karakter, büyük/küçük harf ve boşluk farklarını yok sayan karşılaştırma anahtarı.

    TKGM bazı adları "Gölbaşi" gibi hatalı yazımla döndürdüğü için ad
    eşleştirmeleri her yerde bu anahtar üzerinden yapılır.
    """
    return " ".join(text.translate(_FOLD_TABLE).lower().split())


_PROVINCE_INDEX = {fold(name): price for name, price in PROVINCE_BASE_PRICE.items()}
_DISTRICT_INDEX = {
    fold(province): {fold(district): factor for district, factor in districts.items()}
    for province, districts in DISTRICT_FACTOR.items()
}


def province_base_price(province: str) -> int | None:
    return _PROVINCE_INDEX.get(fold(province))


def district_factor(province: str, district: str) -> float | None:
    return _DISTRICT_INDEX.get(fold(province), {}).get(fold(district))
