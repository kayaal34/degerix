"""
Parselin çevresi: denize ve ana yola mesafe, yakındaki hizmetler, eğim, yerleşim.

Ölçümler app/nearby.py'de OpenStreetMap ve yükselti servisinden alınır. Bunlardan
yalnızca biri değere dokunur: parselin yerleşimin kıyısında olup olmadığı
(settlement_position → app/valuation.py'deki fringe_factor). Kıyı, ana yol, hizmet
ve eğim ölçülüp fiyat etkisi bulunamadığı için dökümde bilgi olarak kalır;
gerekçesi factor_rows'un içinde yazılı.
"""

from dataclasses import dataclass

COAST_RADIUS_M = 3000
MAIN_ROAD_RADIUS_M = 1500
SERVICES_RADIUS_M = 1000
BUILDINGS_RADIUS_M = 400     # "yerleşimin kıyısında mı" ölçümünün yarıçapı
BUILT_UP_RADIUS_M = 3000     # yerleşik alan poligonu bu kadar uzağa kadar aranır
DENSE_BUILDINGS = 50         # bu kadar bina, parselin yerleşimin içinde olduğunu söyler


@dataclass(frozen=True)
class OsmContext:
    coast_m: float | None       # None: COAST_RADIUS_M içinde kıyı yok
    main_road_m: float | None   # None: MAIN_ROAD_RADIUS_M içinde ana yol yok
    services: int               # SERVICES_RADIUS_M içindeki okul, sağlık ve market noktası
    buildings: int = 0          # BUILDINGS_RADIUS_M içindeki bina sayısı
    built_up_m: float | None = None   # yerleşik alan poligonuna m; 0 = içinde, None = yok


@dataclass(frozen=True)
class Surroundings:
    osm: OsmContext | None      # None: OpenStreetMap'e ulaşılamadı
    slope_pct: float | None     # None: yükselti alınamadı


def settlement_position(osm: OsmContext | None) -> str | None:
    """Parselin yerleşime göre yeri: "ic", "kiyi", "kir" ya da ölçülemediyse None.

    Ölçüm şunu gösterdi: imarsız arazide model boş kırda doğru (62 ilanın 27'sinde
    400 m içinde hiç bina yok, ortanca oran 1,00) ve yerleşimin içinde doğru (200+
    bina, 0,78), ama *kıyıda* şaşıyor — 400 m içinde birkaç bina varsa ilan modelin
    2,49 katını istiyor. Sebep anlaşılır: imar beklentisi büyümekte olan yerleşimin
    kenarında doğar, ne ıssız tarlada ne dolmuş merkezde.

    Ölçüt, çizilmiş yerleşik alan sınırına uzaklık değil, görünen binadır. İkisi de
    denendi: "yerleşik alanın 1,5 km'si içinde" ölçütü 30 kaydı kapsayıp 19'unu
    iyileştirip 11'ini bozarken, "400 m içinde bina var" ölçütü 15 kaydı kapsayıp
    12'sini iyileştiriyor ve 3'ünü bozuyor. Fark anlamlı: çizilmiş bir sınırın
    yakınında olmak değil, parselin yanında gerçekten inşaat başlamış olması
    fiyatlanıyor. Poligon uzaklığı yine de okunur — parselin yerleşimin *içinde*
    olup olmadığını söyler ve dökümde kullanıcıya gösterilir.
    """
    if osm is None:
        return None
    if osm.buildings >= DENSE_BUILDINGS or osm.built_up_m == 0:
        return "ic"
    return "kiyi" if osm.buildings >= 1 else "kir"


def position_detail(osm: OsmContext) -> str:
    if osm.built_up_m is None:
        yer = f"{BUILT_UP_RADIUS_M // 1000} km içinde yerleşik alan çizilmemiş"
    elif osm.built_up_m == 0:
        yer = "yerleşik alanın içinde"
    else:
        yer = f"yerleşik alana {_distance(osm.built_up_m)}"
    return f"{yer} · {BUILDINGS_RADIUS_M} m içinde {osm.buildings} bina"


def _distance(meters: float) -> str:
    if meters < 1000:
        return f"{round(meters / 10) * 10:.0f} m"
    return f"{meters / 1000:.1f} km".replace(".", ",")


def factor_rows(surroundings: Surroundings) -> list[tuple[str, str, float, str]]:
    """Çevre ölçümleri dökümde tek bilgi satırı olur; değere dokunmazlar (×1,00).

    Buradaki dört ölçüm başlangıçta katsayıya çevrilmişti: kıyıda ×1,20'ye kadar
    prim, ana yol 1,5 km içinde yoksa ×0,90, hizmet noktası yoksa ×0,95, %25 eğimde
    ×0,85. Hiçbiri ölçülmemişti. 103 ilanda ölçüldüklerinde dördü birlikte modeli
    **bozuyordu**: tipik sapma katsayısızken de ×1,80, ±%50 içindeki kayıt ise
    53'ten 47'ye düşüyordu — kazanç yok, altı kayıt kaybı var. Sebebi, dördünün de
    yalnızca kırpması: Türkiye kırsalında OSM'de ana yol çizilmemiş olması parselin
    yolu olmadığı anlamına gelmiyor, biz eksik veriyi fiyat indirimi sayıyorduk.

    Katsayıları veriden yeniden kurmak da kurtarmadı. Her etken kendi kovalarında
    ortanca oranla kurulup (diğerleri bölünerek, dört tur) en iyi haline getirildiğinde
    bile ±%50 oranı 49'da kaldı, yani nötrün altında; ölçüldüğü kayıtları görerek
    kurulan bir katsayı ×1,00'i geçemiyorsa sahada geçmesi beklenmez. Dışarıda
    bırakmalı ölçüm bunu doğruluyor: her kayıt kendisi hariç kalan 102 kayıttan
    kurulan katsayıyla puanlandığında tipik sapma ×1,98'e çıkıyor ve ±%50 oranı
    45'e düşüyor — dört kovanın ortancası ezberden başka bir şey taşımıyor. Tek tek de
    denendiler: kıyı 11 iyi/15 bozuk, hizmet 51/50, eğim bugünkü haliyle ±%50'yi
    53'ten 47'ye düşüren en zararlı tekil etken (ölçümde %20+ eğimli 13 parsel
    modelin 1,17 katını istiyor — eğim cezası bu veride ters yönde).

    En umutlu aday ana yol primiydi: 150 m içinde yol olan 19 parselde artık oran
    1,52 görünüyordu. Üç sınavın hiçbirini geçmedi — dışarıda bırakmalı ölçümde
    tipik sapma ×1,80'den ×1,82'ye çıktı ve ±%50 53'ten 50'ye düştü, iyileşen/bozulan
    10'a 9, aykırı beş kayıt çıkarıldığında kazanç tamamen kayboldu (×1,68 → ×1,68).
    Primin doğrudan ölçülen büyüklüğü 1,21 ve 19 kaydı oynatıp hiçbir şey
    kazandırmıyor. İlk yazdığımda 1,52'yi "kovaların birbirine bölünmesinden doğan
    bir yankı" diye açıklamıştım; o açıklamayı geri çekiyorum, çünkü ölçmeden
    verilmiş bir hükümdü. 1,52'nin nereden geldiği açıklanmamış durumdadır.

    Reddedilen dört katsayının kendisi tools/cevre_olc.py içinde duruyor; veri
    büyüdüğünde aynı betikle yeniden sınanabilirler.
    """
    osm = surroundings.osm
    parcalar: list[str] = []
    if osm is not None:
        parcalar.append(f"kıyıya {_distance(osm.coast_m)}" if osm.coast_m is not None
                        else f"{COAST_RADIUS_M // 1000} km içinde kıyı yok")
        parcalar.append(f"ana yola {_distance(osm.main_road_m)}" if osm.main_road_m is not None
                        else "1,5 km içinde ana yol yok")
        parcalar.append(f"1 km içinde {osm.services} okul, sağlık ya da market noktası")
    if surroundings.slope_pct is not None:
        parcalar.append(f"eğim yaklaşık %{surroundings.slope_pct:.0f}")
    if not parcalar:
        return []
    anlatim = " · ".join(parcalar)
    return [("surroundings", "Çevre ölçümleri", 1.0,
             f"{anlatim[0].upper()}{anlatim[1:]} · 103 ilanda fiyat etkisi ölçülemedi")]
