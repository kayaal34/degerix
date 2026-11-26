"""Ölçüm araçlarının ortak tanımları (ilan_karsilastir, cevre_olc, yerlesim_olc, calibrate).

İki tanım burada tek yerde durur; araçlar kendi kopyasını yazmaz.
"""

ESIK_KAT = 1.5


def yarim_kat_icinde(oran: float, kat: float = ESIK_KAT) -> bool:
    """1/kat <= oran <= kat. Değerleme hatası çarpımsaldır: 2 kat şişirmek ile
    yarıya düşürmek aynı büyüklükte hatadır; abs(oran-1) <= 0.5 bunu asimetrik sayıyordu
    (0,5-1,5 aralığı; çarpımsalı 0,667-1,5)."""
    return 1 / kat <= oran <= kat


ETIKET = "1,5 kat içinde"


def hedef_tl(deger_tl: float, tur, indirim: float):
    """İlan/satış değerini 'gerçekleşen satış' eşdeğerine çevirir.

    "satis" -> olduğu gibi; "ilan" -> pazarlık payı düşülür (indirim = model_params
    asking_discount). Tanınmayan/boş tür -> None: çağıran kaydı ölçüm dışı bırakır.
    Gerekçe: sessizce satış ya da ilan varsaymak ölçümü gizlice bozar; istisna
    fırlatmak ise tek bir kötü satır yüzünden uzun (Overpass) toplu koşuyu öldürür.
    """
    tur = (tur or "").strip()
    if tur == "satis":
        return deger_tl
    if tur == "ilan":
        return deger_tl * (1 - indirim)
    return None
