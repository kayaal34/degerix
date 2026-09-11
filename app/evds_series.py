"""
TCMB EVDS seri kodları (evds3 kataloğundan alındı, Eylül 2026).

    Konut birim fiyatı (TL/m², üç aylık)   TP.BIRIMFIYAT.<kod>   veri grubu bie_birimfiyat
    Konut fiyat endeksi (aylık, bölge)     TP.KFE.<bölge>        veri grubu bie_kfe
    Konut satış sayısı (aylık, il)         TP.AKONUTSAT1.<kod>   veri grubu bie_akonutsat1
"""

UNIT_PRICE_PREFIX = "TP.BIRIMFIYAT."
PRICE_INDEX_PREFIX = "TP.KFE."
SALES_PREFIX = "TP.AKONUTSAT1."

# Konut fiyat endeksi bölgeleri ve kapsadıkları iller
PRICE_INDEX_REGIONS: dict[str, tuple[str, ...]] = {
    "TR10": ("İstanbul",),
    "TR51": ("Ankara",),
    "TR31": ("İzmir",),
    "TR21": ("Edirne", "Kırklareli", "Tekirdağ"),
    "TR22": ("Balıkesir", "Çanakkale"),
    "TR32": ("Aydın", "Denizli", "Muğla"),
    "TR33": ("Afyonkarahisar", "Kütahya", "Manisa", "Uşak"),
    "TR41": ("Bursa", "Eskişehir", "Bilecik"),
    "TR42": ("Bolu", "Kocaeli", "Sakarya", "Yalova", "Düzce"),
    "TR52": ("Konya", "Karaman"),
    "TR61": ("Antalya", "Burdur", "Isparta"),
    "TR62": ("Adana", "Mersin"),
    "TR63": ("Hatay", "Kahramanmaraş", "Osmaniye"),
    "TR7": ("Nevşehir", "Niğde", "Kırıkkale", "Kırşehir", "Aksaray", "Kayseri", "Sivas", "Yozgat"),
    "TR8": ("Zonguldak", "Karabük", "Bartın", "Kastamonu", "Çankırı", "Sinop", "Samsun", "Tokat", "Çorum", "Amasya"),
    "TR9": ("Trabzon", "Ordu", "Giresun", "Rize", "Artvin", "Gümüşhane"),
    "TRA": ("Erzurum", "Erzincan", "Bayburt", "Ağrı", "Kars", "Iğdır", "Ardahan"),
    "TRB": ("Malatya", "Elazığ", "Bingöl", "Tunceli", "Van", "Muş", "Bitlis", "Hakkari"),
    "TRC": ("Gaziantep", "Adıyaman", "Kilis", "Şanlıurfa", "Diyarbakır", "Mardin", "Batman", "Şırnak", "Siirt"),
}

# İl → birim fiyat serisi. Ardahan, Bayburt, Gümüşhane, Hakkari ve Tunceli için
# yeterli veri olmadığından TCMB birim fiyat yayımlamıyor.
UNIT_PRICE_SERIES: dict[str, str] = {
    "Adana": "ADANA", "Adıyaman": "ADIYAMAN", "Afyonkarahisar": "AFYON", "Ağrı": "AGRI",
    "Aksaray": "AKSARAY", "Amasya": "AMASYA", "Ankara": "ANK", "Antalya": "ANTALYA",
    "Artvin": "ARTVIN", "Aydın": "AYDIN", "Balıkesir": "BALIKESIR", "Bartın": "BARTIN",
    "Batman": "BATMAN", "Bilecik": "BILECIK", "Bingöl": "BINGOL", "Bitlis": "BITLIS",
    "Bolu": "BOLU", "Burdur": "BURDUR", "Bursa": "BURSA", "Çanakkale": "CANAKKALE",
    "Çankırı": "CANKIRI", "Çorum": "CORUM", "Denizli": "DENIZLI", "Diyarbakır": "DIYARBAKIR",
    "Düzce": "DUZCE", "Edirne": "EDIRNE", "Elazığ": "ELAZIG", "Erzincan": "ERZINCAN",
    "Erzurum": "ERZURUM", "Eskişehir": "ESKISEHIR", "Gaziantep": "ANTEP", "Giresun": "GIRESUN",
    "Hatay": "HATAY", "Iğdır": "IGDIR", "Isparta": "ISPARTA", "İstanbul": "IST",
    "İzmir": "IZM", "Kahramanmaraş": "MARAS", "Karabük": "KARABUK", "Karaman": "KARAMAN",
    "Kars": "KARS", "Kastamonu": "KASTAMONU", "Kayseri": "KAYSERI", "Kilis": "KILIS",
    "Kırıkkale": "KIRIKKALE", "Kırklareli": "KIRKLARELI", "Kırşehir": "KIRSEHIR", "Kocaeli": "KOCAELI",
    "Konya": "KONYA", "Kütahya": "KUTAHYA", "Malatya": "MALATYA", "Manisa": "MANISA",
    "Mardin": "MARDIN", "Mersin": "MERSIN", "Muğla": "MUGLA", "Muş": "MUS",
    "Nevşehir": "NEVSEHIR", "Niğde": "NIGDE", "Ordu": "ORDU", "Osmaniye": "OSMANIYE",
    "Rize": "RIZE", "Sakarya": "SAKARYA", "Samsun": "SAMSUN", "Siirt": "SIIRT",
    "Sinop": "SINOP", "Sivas": "SIVAS", "Şanlıurfa": "URFA", "Şırnak": "SIRNAK",
    "Tekirdağ": "TEKIRDAG", "Tokat": "TOKAT", "Trabzon": "TRABZON", "Uşak": "USAK",
    "Van": "VAN", "Yalova": "YALOVA", "Yozgat": "YOZGAT", "Zonguldak": "ZONGULDAK",
}

# İl → konut satış serisi (İBBS-3 kodu)
SALES_SERIES: dict[str, str] = {
    "Adana": "KTR621", "Adıyaman": "KTRC12", "Afyonkarahisar": "KTR332", "Ağrı": "KTRA21",
    "Aksaray": "KTR712", "Amasya": "KTR834", "Ankara": "KTR510", "Antalya": "KTR611",
    "Ardahan": "KTRA24", "Artvin": "KTR905", "Aydın": "KTR321", "Balıkesir": "KTR221",
    "Bartın": "KTR813", "Batman": "KTRC32", "Bayburt": "KTRA13", "Bilecik": "KTR413",
    "Bingöl": "KTRB13", "Bitlis": "KTRB23", "Bolu": "KTR424", "Burdur": "KTR613",
    "Bursa": "KTR411", "Çanakkale": "KTR222", "Çankırı": "KTR822", "Çorum": "KTR833",
    "Denizli": "KTR322", "Diyarbakır": "KTRC22", "Düzce": "KTR423", "Edirne": "KTR212",
    "Elazığ": "KTRB12", "Erzincan": "KTRA12", "Erzurum": "KTRA11", "Eskişehir": "KTR412",
    "Gaziantep": "KTRC11", "Giresun": "KTR903", "Gümüşhane": "KTR906", "Hakkari": "KTRB24",
    "Hatay": "KTR631", "Iğdır": "KTRA23", "Isparta": "KTR612", "İstanbul": "KTR100",
    "İzmir": "KTR310", "Kahramanmaraş": "KTR632", "Karabük": "KTR812", "Karaman": "KTR522",
    "Kars": "KTRA22", "Kastamonu": "KTR821", "Kayseri": "KTR721", "Kırıkkale": "KTR711",
    "Kırklareli": "KTR213", "Kırşehir": "KTR715", "Kilis": "KTRC13", "Kocaeli": "KTR421",
    "Konya": "KTR521", "Kütahya": "KTR333", "Malatya": "KTRB11", "Manisa": "KTR331",
    "Mardin": "KTRC31", "Mersin": "KTR622", "Muğla": "KTR323", "Muş": "KTRB22",
    "Nevşehir": "KTR714", "Niğde": "KTR713", "Ordu": "KTR902", "Osmaniye": "KTR633",
    "Rize": "KTR904", "Sakarya": "KTR422", "Samsun": "KTR831", "Siirt": "KTRC34",
    "Sinop": "KTR823", "Sivas": "KTR722", "Şanlıurfa": "KTRC21", "Şırnak": "KTRC33",
    "Tekirdağ": "KTR211", "Tokat": "KTR832", "Trabzon": "KTR901", "Tunceli": "KTRB14",
    "Uşak": "KTR334", "Van": "KTRB21", "Yalova": "KTR425", "Yozgat": "KTR723",
    "Zonguldak": "KTR811",
}
