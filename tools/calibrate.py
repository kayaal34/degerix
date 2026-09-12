"""
Modelin hatasını ölçer ve yerleşim katsayılarını gerçek kayıtlara göre ayarlar.

    python tools/calibrate.py            # yalnızca rapor
    python tools/calibrate.py --uygula   # app/static_data/calibration.json dosyasını yazar

Okunan kayıtlar:
    data/pilot/*.csv     kaynağı belli, kamuya açık kayıtlar (depoda)
    data/private/*.csv   elle derlenen doğrulama kayıtları (git'e gönderilmez)

Beklenen sütunlar: il, lat, lng, alan_m2, imar, deger_tl, deger_turu
İsteğe bağlı: emsal, tapu, yol, elektrik_su, manzara, kose, sulama, ilce, kaynak_url

deger_turu "ilan" ise, ilan fiyatı satış fiyatı olmadığı için model_params içindeki
pazarlık payı kadar indirilerek karşılaştırılır.

Yöntem: her yerleşim sınıfı için modelin sistematik sapması ölçülür ve o sınıfın
katsayısı sapmanın ortancasıyla düzeltilir (üç geçiş). Az kayıtlı sınıflara
dokunulmaz; böylece birkaç ilan yüzünden katsayılar savrulmaz.
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

from dotenv import load_dotenv  # noqa: E402

from app import market, urbanity  # noqa: E402
from app.model_params import CALIBRATION_FILE, DEFAULTS, Parameters  # noqa: E402
from app.valuation import estimate  # noqa: E402

PILOT_DIR = ROOT / "data" / "pilot"
PRIVATE_DIR = ROOT / "data" / "private"

MIN_RECORDS_PER_CLASS = 5   # bu sayının altındaki sınıfın katsayısına dokunulmaz
MAX_ADJUSTMENT = 2.0        # katsayı en fazla iki katına çıkar ya da yarıya iner
PASSES = 3

ANSWER_COLUMNS = {
    "tapu": "deed", "yol": "road", "elektrik_su": "utilities",
    "manzara": "view", "kose": "corner", "sulama": "irrigation",
}


def read_records() -> list[dict[str, str]]:
    records = []
    for directory in (PILOT_DIR, PRIVATE_DIR):
        for path in sorted(directory.glob("*.csv")) if directory.exists() else []:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row.get("deger_tl") and row.get("lat") and row.get("il"):
                        row["_kaynak"] = path.name
                        records.append(row)
    return records


def number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(".", "").replace(",", ".")) if "," in value else float(value)
    except ValueError:
        return None


async def predict(record: dict[str, str], parameters: Parameters) -> float | None:
    """Kaydın model tahmini (TL)."""
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
    return float(result.total)


async def evaluate(records: list[dict[str, str]], parameters: Parameters) -> list[tuple[dict, float, float, int]]:
    """(kayıt, hedef değer, tahmin, yerleşim sınıfı) listesi."""
    rows = []
    for record in records:
        target = number(record.get("deger_tl"))
        prediction = await predict(record, parameters)
        if not target or not prediction:
            continue
        if (record.get("deger_turu") or "").strip() == "ilan":
            target *= 1 - parameters.asking_discount
        place = urbanity.describe(float(record["lat"]), float(record["lng"]))
        rows.append((record, target, prediction, place.class_code if place else urbanity.LOW_RURAL))
    return rows


def report(rows: list[tuple[dict, float, float, int]]) -> dict:
    errors = [abs(math.log(target / prediction)) for _, target, prediction, _ in rows]
    within = sum(1 for error in errors if error <= math.log(1.25))
    summary = {
        "kayit": len(rows),
        "ortanca_sapma_yuzde": round((math.exp(statistics.median(errors)) - 1) * 100, 1) if errors else None,
        "yuzde_25_icinde": round(100 * within / len(rows), 1) if rows else None,
    }
    print(f"\nkayıt: {summary['kayit']} · ortanca sapma: %{summary['ortanca_sapma_yuzde']} · "
          f"±%25 içinde: %{summary['yuzde_25_icinde']}")

    by_class: dict[int, list[float]] = {}
    for _, target, prediction, class_code in rows:
        by_class.setdefault(class_code, []).append(math.log(target / prediction))
    for class_code, ratios in sorted(by_class.items(), reverse=True):
        direction = "düşük" if statistics.median(ratios) > 0 else "yüksek"
        print(f"  {urbanity.CLASS_LABELS[class_code]:<20} {len(ratios):>3} kayıt · "
              f"model ortalama %{abs(math.exp(statistics.median(ratios)) - 1) * 100:.0f} {direction}")
    return summary


async def fit(records: list[dict[str, str]], parameters: Parameters) -> tuple[Parameters, dict]:
    """Yerleşim katsayılarını kayıtlara göre düzeltir."""
    summary = {}
    for pass_number in range(1, PASSES + 1):
        rows = await evaluate(records, parameters)
        summary = report(rows)
        by_class: dict[int, list[float]] = {}
        for _, target, prediction, class_code in rows:
            by_class.setdefault(class_code, []).append(math.log(target / prediction))

        locality = dict(parameters.locality)
        for class_code, ratios in by_class.items():
            if len(ratios) < MIN_RECORDS_PER_CLASS:
                continue
            correction = math.exp(statistics.median(ratios))
            prior = DEFAULTS.locality[class_code]
            adjusted = locality[class_code] * correction
            locality[class_code] = round(min(max(adjusted, prior / MAX_ADJUSTMENT), prior * MAX_ADJUSTMENT), 3)
        parameters = replace(parameters, locality=locality)
    return parameters, summary


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
    for class_code, value in sorted(fitted.locality.items(), reverse=True):
        mark = "" if value == DEFAULTS.locality[class_code] else f"  (varsayılan {DEFAULTS.locality[class_code]})"
        print(f"  {urbanity.CLASS_LABELS[class_code]:<20} {value}{mark}")

    if not arguments.uygula:
        print("\nYazmak için: python tools/calibrate.py --uygula")
        return

    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_FILE.write_text(
        json.dumps(
            {
                "kaynak": f"kalibrasyon {date.today().isoformat()} ({len(records)} kayıt)",
                "rapor": {"once": before, "sonra": after},
                "parametreler": {"locality": {str(key): value for key, value in fitted.locality.items()}},
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
