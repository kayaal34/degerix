"""
Modelin hatasını ölçer ve yerleşim katsayılarını gerçek kayıtlara göre ayarlar.

    python tools/calibrate.py            # yalnızca rapor
    python tools/calibrate.py --uygula   # app/static_data/calibration.json dosyasını yazar

Okunan kayıtlar:
    data/pilot/*.csv     kaynağı belli, kamuya açık kayıtlar (depoda)
    data/private/*.csv   elle derlenen doğrulama kayıtları (git'e gönderilmez)

Beklenen sütunlar: il, lat, lng, alan_m2, imar, deger_tl, deger_turu
İsteğe bağlı: emsal, tapu, yol, elektrik_su, manzara, kose, sulama, ilce, kaynak_url
haric sütunu doluysa kayıt dosyada kalır ama ölçüme girmez (ör. yapili, spekulatif).

deger_turu "ilan" ise, ilan fiyatı satış fiyatı olmadığı için model_params içindeki
pazarlık payı kadar indirilerek karşılaştırılır.

Yöntem: her yerleşim sınıfı için modelin sistematik sapması ölçülür ve o sınıfın
katsayısı sapmanın ortancasıyla düzeltilir (üç geçiş). Az kayıtlı sınıflara
dokunulmaz; böylece birkaç ilan yüzünden katsayılar savrulmaz.

İmarlı ve imarsız kayıtlar ayrı katsayıları besler: imarlı arsa yerleşim katsayısını
(locality), imarsız arazi ise arazi oranını (farmland_ratio) ayarlar. İkisi tek
katsayıdan ayarlansaydı tarlayı düzeltmek imarlı arsayı bozardı.
"""

import argparse
import asyncio
import csv
import json
import math
import statistics
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from dotenv import load_dotenv  # noqa: E402

from app import market, urbanity  # noqa: E402
from app.model_params import CALIBRATION_FILE, DEFAULTS, Parameters  # noqa: E402
from app.valuation import effective_class, estimate  # noqa: E402
from olcum_ortak import hedef_tl  # noqa: E402

PILOT_DIR = ROOT / "data" / "pilot"
PRIVATE_DIR = ROOT / "data" / "private"

MIN_RECORDS_PER_CLASS = 5   # bu sayının altındaki sınıfın katsayısına dokunulmaz
PASSES = 3

# Ölçülen sapma katsayıya olduğu gibi yazılmaz, varsayılana doğru büzülür.
# İki gerekçe: az kayıt gürültülüdür ve tek bölgeden gelen kayıt ülkeye genellenemez.
# Marmara ovasındaki tarla ilanlarına bakıp Erzurum'un tarlasını pahalılandırmayalım.
PRIOR_STRENGTH = 10         # bu kadar kayıt, varsayılanla yarı yarıya ağırlık demek
PROVINCE_TARGET = 5         # tam güven için gereken farklı il sayısı

# Ayarlanan katsayılar: (alan adı, varsayılandan en çok kaç kat sapabilir).
# locality'nin bandı dar: TCMB'nin il konut fiyatı ölçülmüş bir veridir, yerleşim
# katsayısı onun üstüne küçük bir düzeltmedir. farmland_ratio ise veriye dayanmayan
# bir ilk tahmindi, o yüzden daha geniş bir bantta ayarlanabilir.
FITTED = {"locality": 2.0, "farmland_ratio": 3.0}

# Hangi kullanım hangi katsayıyı besler
UNZONED = {"tarla", "bag_bahce", "zeytinlik"}

ANSWER_COLUMNS = {
    "tapu": "deed", "yol": "road", "elektrik_su": "utilities",
    "manzara": "view", "kose": "corner", "sulama": "irrigation",
}


def read_records() -> list[dict[str, str]]:
    """Katsayı ayarlamaya uygun kayıtlar: yalnızca koordinatı parselin kendisi olanlar.

    `konum` sütunu "mahalle" ise koordinat mahalle merkezidir, parselin değil.
    O kayıtlarda yerleşim sınıfı, yerleşime uzaklık ve erişilebilirlik parselin
    değil köy çekirdeğinin ölçümüdür; katsayı sınıf başına ayarlandığı için
    sapma yanlış sınıfa yazılır. Ölçümde bu fark açıkça görülüyor: mahalle
    merkezli kayıtlarda model isabetli görünüyor (medyan 0,97) ama gerçek parsel
    koordinatlarında %50 düşük (medyan 1,50). İlk gruptan öğrenmek, modeli
    kendi ölçüm hatasına uydurmak olurdu.
    """
    records, elenen = [], 0
    for directory in (PILOT_DIR, PRIVATE_DIR):
        for path in sorted(directory.glob("*.csv")) if directory.exists() else []:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if (row.get("haric") or "").strip():
                        continue
                    if not (row.get("deger_tl") and row.get("lat") and row.get("il")):
                        continue
                    if (row.get("konum") or "").strip() != "parsel":
                        elenen += 1
                        continue
                    row["_kaynak"] = path.name
                    records.append(row)
    if elenen:
        print(f"{elenen} kayıt ayrıldı: koordinatı parselin değil mahalle merkezinin "
              f"(konum sütunu). Ölçüm için tools/ilan_karsilastir.py hepsini gösterir.")
    return records


def number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(".", "").replace(",", ".")) if "," in value else float(value)
    except ValueError:
        return None


async def predict(record: dict[str, str], parameters: Parameters) -> tuple[float, str] | None:
    """Kaydın model tahmini: (TL, kullanılan yöntem)."""
    area = number(record.get("alan_m2"))
    if not area:
        return None
    housing = market.snapshot_price(record["il"])
    if housing is None:
        print(f"  {record['_kaynak']}: {record['il']} tanınmadı, atlandı")
        return None

    answers = {}
    for column, field in ANSWER_COLUMNS.items():
        value = (record.get(column) or "").strip()
        if value:
            answers[field] = value

    result = estimate(
        area_m2=area,
        usage=(record.get("imar") or "konut").strip(),
        housing=housing,
        urban=urbanity.describe(float(record["lat"]), float(record["lng"])),
        kaks=number(record.get("emsal")),
        parameters=parameters,
        **answers,
    )
    return float(result.total), result.basis


async def evaluate(records: list[dict[str, str]], parameters: Parameters) -> list[tuple[dict, float, float, int, str]]:
    """(kayıt, hedef değer, tahmin, yerleşim sınıfı, yöntem) listesi.

    Yerleşim sınıfı, modelin katsayıyı hangi sınıftan okuduğudur: hücrenin ham
    sınıfı değil, erişilebilirlikle birlikte oluşan etkin sınıf. İkisi
    ayrıldığından beri ham sınıfı kullanmak sapmayı yanlış katsayıya yazıyordu —
    Kayapınar şehir merkezi oranıyla fiyatlanırken düzeltme seyrek kırsala
    gidiyordu, yani her geçişte yanlış katsayı oynuyordu.
    """
    rows = []
    for record in records:
        target = number(record.get("deger_tl"))
        prediction = await predict(record, parameters)
        if not target or not prediction:
            continue
        # Tanınmayan/boş deger_turu ölçüm dışı (sessizce satış sayılmaz).
        target = hedef_tl(target, record.get("deger_turu"), parameters.asking_discount)
        if target is None:
            continue
        place = urbanity.describe(float(record["lat"]), float(record["lng"]))
        rows.append((record, target, prediction[0], effective_class(place), prediction[1]))
    return rows


def report(rows: list[tuple[dict, float, float, int, str]]) -> dict:
    errors = [abs(math.log(target / prediction)) for _, target, prediction, _, _ in rows]
    within = sum(1 for error in errors if error <= math.log(1.25))
    summary = {
        "kayit": len(rows),
        "ortanca_sapma_yuzde": round((math.exp(statistics.median(errors)) - 1) * 100, 1) if errors else None,
        # Aday seçimi bu sayıya göre yapılır. Ortanca sapma kuyrukları hiç görmez:
        # iki kat yanılan tek bir kayıt onu kıpırdatmaz. Oysa ürünün gösterdiği değer
        # aralığı tam olarak kuyrukla ilgili ve projenin her yerinde kullanılan ölçüt
        # çarpımsal tipik sapmadır (ort|log2|). Ortanca sapmaya göre seçmek, emsal
        # sönümlemesinden sonra tipik sapmayı 0,86'dan 0,96'ya çıkaran katsayı setini
        # "daha iyi" sanmaya yol açıyordu.
        "tipik_sapma_kat": round(math.exp(statistics.mean(errors)), 3) if errors else None,
        "yuzde_25_icinde": round(100 * within / len(rows), 1) if rows else None,
    }
    print(f"\nkayıt: {summary['kayit']} · ortanca sapma: %{summary['ortanca_sapma_yuzde']} · "
          f"tipik sapma: ×{summary['tipik_sapma_kat']} · "
          f"±%25 içinde: %{summary['yuzde_25_icinde']}")

    for group, label in ((False, "imarlı arsa"), (True, "imarsız arazi")):
        selected = [row for row in rows if is_unzoned(row[0]) == group]
        if not selected:
            continue
        print(f"  {label}:")
        by_class: dict[int, list[float]] = {}
        for _, target, prediction, class_code, _basis in selected:
            by_class.setdefault(class_code, []).append(math.log(target / prediction))
        for class_code, ratios in sorted(by_class.items(), reverse=True):
            direction = "düşük" if statistics.median(ratios) > 0 else "yüksek"
            print(f"    {urbanity.CLASS_LABELS[class_code]:<20} {len(ratios):>3} kayıt · "
                  f"model ortalama %{abs(math.exp(statistics.median(ratios)) - 1) * 100:.0f} {direction}")
    return summary


def is_unzoned(record: dict[str, str]) -> bool:
    return (record.get("imar") or "").strip() in UNZONED


def confidence(ratios: list[float], provinces: set[str]) -> float:
    """Ölçülen sapmanın ne kadarının katsayıya yazılacağı (0 ile 1 arası)."""
    sample = len(ratios) / (len(ratios) + PRIOR_STRENGTH)
    spread = min(1.0, len(provinces) / PROVINCE_TARGET)
    return sample * spread


def fit_one(rows, parameters: Parameters, name: str) -> dict[int, float]:
    """Bir katsayı sözlüğünü, onu besleyen kayıtların sapma ortancasıyla düzeltir."""
    by_class: dict[int, tuple[list[float], set[str]]] = {}
    for record, target, prediction, class_code, _basis in rows:
        ratios, provinces = by_class.setdefault(class_code, ([], set()))
        ratios.append(math.log(target / prediction))
        provinces.add(record["il"])

    values = dict(getattr(parameters, name))
    defaults, limit = getattr(DEFAULTS, name), FITTED[name]
    for class_code, (ratios, provinces) in by_class.items():
        if len(ratios) < MIN_RECORDS_PER_CLASS:
            continue
        prior = defaults[class_code]
        adjusted = values[class_code] * math.exp(statistics.median(ratios))
        # Veriye tam uyan değer bulunur, sonra güvenilirlik kadarı varsayılandan uzaklaşır
        adjusted = prior * (adjusted / prior) ** confidence(ratios, provinces)
        values[class_code] = round(min(max(adjusted, prior / limit), prior * limit), 4)
    return values


async def fit(records: list[dict[str, str]], parameters: Parameters) -> tuple[Parameters, dict]:
    """İmarlı kayıtlardan yerleşim katsayısını, imarsızlardan arazi oranını ayarlar."""
    # Her geçişin sonucu ölçülür ve en iyisi tutulur. Eskiden döngü son geçişin
    # katsayısını döndürüyor ama bir önceki geçişin raporunu yazıyordu: dosyaya
    # yazılan sayı ile ölçülen sayı aynı duruma ait değildi. Dahası fit tek yönlü
    # yakınsamıyor — locality hem imarlıyı hem imarsızı kaydırdığı için ölçüm
    # 96,8 → 66,8 → 78,2 diye salınıyor. "Son geçiş" bu yüzden doğru cevap değil;
    # ölçülmüş en iyi aday doğru cevaptır ve varsayılanlar da adaylardan biridir.
    summary = report(await evaluate(records, parameters))
    best, best_summary = parameters, summary
    for _ in range(PASSES):
        rows = await evaluate(records, parameters)
        zoned = [row for row in rows if not is_unzoned(row[0])]
        # farmland_ratio yalnızca onu gerçekten kullanan kayıtlardan ayarlanır:
        # imar beklentisiyle fiyatlanan parselde bu oranın hiçbir etkisi yok, o
        # kayıtların sapmasını buraya yazmak oranı boşuna savurur.
        unzoned = [row for row in rows if is_unzoned(row[0]) and row[4] == "arazi"]
        parameters = replace(
            parameters,
            locality=fit_one(zoned, parameters, "locality"),
            farmland_ratio=fit_one(unzoned, parameters, "farmland_ratio"),
        )
        summary = report(await evaluate(records, parameters))
        if summary["tipik_sapma_kat"] < best_summary["tipik_sapma_kat"]:
            best, best_summary = parameters, summary
    return best, best_summary


async def main() -> None:
    parser = argparse.ArgumentParser(description="Değerix kalibrasyonu")
    parser.add_argument("--uygula", action="store_true", help="katsayıları calibration.json dosyasına yaz")
    arguments = parser.parse_args()

    load_dotenv(ROOT / ".env")
    records = read_records()
    if not records:
        sys.exit(
            "Kayıt bulunamadı.\n"
            "  data/pilot/*.csv ya da data/private/*.csv içine en az bir satır ekleyin.\n"
            "  Gerekli sütunlar: il, lat, lng, alan_m2, imar, deger_tl, deger_turu"
        )
    print(f"{len(records)} kayıt okundu")

    print("\n--- varsayılan katsayılarla ---")
    before = report(await evaluate(records, DEFAULTS))

    fitted, after = await fit(records, DEFAULTS)
    print("\n--- ayarlanmış katsayılar ---")
    for name in FITTED:
        print(f"  {name}:")
        defaults = getattr(DEFAULTS, name)
        for class_code, value in sorted(getattr(fitted, name).items(), reverse=True):
            mark = "" if value == defaults[class_code] else f"  (varsayılan {defaults[class_code]})"
            print(f"    {urbanity.CLASS_LABELS[class_code]:<20} {value}{mark}")

    if not arguments.uygula:
        print("\nYazmak için: python tools/calibrate.py --uygula")
        return

    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_FILE.write_text(
        json.dumps(
            {
                "kaynak": f"kalibrasyon {date.today().isoformat()} ({len(records)} kayıt)",
                "rapor": {"once": before, "sonra": after},
                "parametreler": {
                    name: {str(key): value for key, value in getattr(fitted, name).items()}
                    for name in FITTED
                },
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nyazıldı: {CALIBRATION_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
