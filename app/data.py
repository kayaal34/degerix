"""
Değerleme sorularının seçenekleri ve katsayıları.

İl bazında konut fiyatları TCMB EVDS'ten (app/market.py), inşaat maliyetleri Resmî
Gazete tebliğinden (app/costs.py), yerleşim sınıfı uydu nüfus verisinden
(app/urbanity.py) gelir. Bu dosyada yalnızca kullanıcı yanıtlarının karşılıkları,
satış senaryoları ve Türkçe ad eşleştirme yardımcısı bulunur.

Buradaki katsayılar başlangıç varsayımıdır. Kalibrasyonla ayarlananlar
app/model_params.py içinde tutulur.
"""

from typing import Literal

UsageKey = Literal["konut", "ticari", "sanayi", "bag_bahce", "zeytinlik", "tarla"]

# İmar durumu etiketleri. Fiyata etkisi app/model_params.py katsayılarıyla hesaplanır.
USAGE: dict[str, str] = {
    "konut": "Konut imarlı",
    "ticari": "Ticari imarlı",
    "sanayi": "Sanayi imarlı",
    "bag_bahce": "İmarsız · bağ / bahçe",
    "zeytinlik": "İmarsız · zeytinlik",
    "tarla": "İmarsız · tarla",
}

# Kullanıcının "bilmiyorum" dediği sorular bu değeri alır
UNKNOWN = "bilinmiyor"

DeedKey = Literal["tam", "hisseli", "bilinmiyor"]
RoadKey = Literal["var", "yok", "bilinmiyor"]
UtilitiesKey = Literal["var", "kismen", "yok", "bilinmiyor"]
IrrigationKey = Literal["sulu", "kuru", "bilinmiyor"]
ViewKey = Literal["var", "yok", "bilinmiyor"]
CornerKey = Literal["evet", "hayir", "bilinmiyor"]

# Hisseli tapuda ortaklık ve satış güçlüğü nedeniyle piyasa indirimi uygulanır
DEED: dict[str, tuple[str, float]] = {
    "tam": ("Müstakil tapu", 1.00),
    "hisseli": ("Hisseli tapu, ortaklık indirimi", 0.80),
}

# Hesap yola cepheli parseli varsayar
ROAD: dict[str, tuple[str, float]] = {
    "var": ("Yola cephesi var", 1.00),
    "yok": ("Yola cephesi yok, geçit hakkı gerekir", 0.75),
}

# (etiket, imarlı arsada katsayı, imarsız arazide katsayı). Tarlada altyapı
# beklentisi zaten düşük olduğundan eksikliğin etkisi daha azdır.
UTILITIES: dict[str, tuple[str, float, float]] = {
    "var": ("Elektrik ve su var", 1.00, 1.00),
    "kismen": ("Elektrik ya da sudan yalnızca biri var", 0.93, 0.98),
    "yok": ("Elektrik ve su yok", 0.85, 0.95),
}

# İmarsız arazide sulama imkânı
IRRIGATION: dict[str, tuple[str, float]] = {
    "sulu": ("Sulu arazi", 1.20),
    "kuru": ("Kuru arazi", 0.90),
}

# Hesap manzarasız ve köşe olmayan parseli varsayar; bu yüzden bu iki soruda
# "bilmiyorum" yanıtı aralığı genişletmez, "yok / hayır" gibi değerlendirilir.
VIEW: dict[str, tuple[str, float]] = {
    "var": ("Deniz ya da göl manzarası var", 1.12),
    "yok": ("Manzara yok", 1.00),
}
CORNER: dict[str, tuple[str, float]] = {
    "evet": ("Köşe parsel, iki yola cephe", 1.08),
    "hayir": ("Köşe parsel değil", 1.00),
}

# Arazi daha yavaş el değiştirdiğinden acele satışta indirim daha derindir.
# Fiyat senaryoları: tahmine uygulanan SABİT oranlar.
#
# Üçüncü sütun eskiden süre yazıyordu — "1–2 ay içinde", "3–6 ay",
# "6 ay ve üzeri". Hiçbiri ölçülmedi: elimizde tek bir satışın ne kadar
# sürdüğüne dair veri yok, olmadığı gibi ilan verisinden de çıkmaz.
# Kullanıcıya "bu fiyata koyarsan iki ayda satarsın" demek, bilmediğimiz
# bir şeyi söylemekti. Artık üçüncü sütun süre değil, senaryonun ne
# anlama geldiği; oranın kendisi arayüzde çarpandan üretiliyor.
#
# Oranlar da ölçülmedi, sektörde yaygın kabul edilen değerlerdir ve
# arayüzde bu açıkça yazıyor. İmarsız arazide makas daha geniş, çünkü
# alıcı havuzu dar.
SALE_SCENARIOS: list[tuple[str, str, str, float, float]] = [
    ("acil", "Acil satış", "Hızlı satmak isteyen için alt uç", 0.85, 0.78),
    ("piyasa", "Piyasa değeri", "Modelin tahmini", 1.00, 1.00),
    ("tok", "Tok satıcı", "Beklemeye razı olan için üst uç", 1.08, 1.10),
]


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
