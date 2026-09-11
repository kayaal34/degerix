"""Coğrafi yardımcılar: iki nokta arası mesafe, poligon merkezi ve alanı."""

import math
from typing import Any

EARTH_RADIUS_KM = 6371.0088
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LNG_AT_EQUATOR = 111.320


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _outer_rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if kind == "Polygon":
        return coordinates[:1]
    if kind == "MultiPolygon":
        return [polygon[0] for polygon in coordinates if polygon]
    raise ValueError(f"Desteklenmeyen geometri türü: {kind}")


def centroid_and_area(geometry: dict[str, Any]) -> tuple[float, float, float]:
    """GeoJSON Polygon/MultiPolygon için (enlem, boylam, alan km²).

    Delikler yok sayılır. Türkiye ölçeğinde eş dikdörtgen projeksiyon bu amaç
    için yeterince hassastır.
    """
    rings = _outer_rings(geometry)
    points = [point for ring in rings for point in ring]
    if not points:
        raise ValueError("Geometri boş.")

    ref_lat = sum(point[1] for point in points) / len(points)
    kx = KM_PER_DEG_LNG_AT_EQUATOR * math.cos(math.radians(ref_lat))
    ky = KM_PER_DEG_LAT

    total_area = weighted_x = weighted_y = 0.0
    for ring in rings:
        projected = [(point[0] * kx, point[1] * ky) for point in ring]
        area = sum_x = sum_y = 0.0
        for (x1, y1), (x2, y2) in zip(projected, projected[1:] + projected[:1]):
            cross = x1 * y2 - x2 * y1
            area += cross
            sum_x += (x1 + x2) * cross
            sum_y += (y1 + y2) * cross
        area /= 2
        if area < 0:  # halka yönünden bağımsız olsun
            area, sum_x, sum_y = -area, -sum_x, -sum_y
        total_area += area
        weighted_x += sum_x / 6
        weighted_y += sum_y / 6

    if total_area < 1e-12:  # dejenere geometri: köşelerin ortalaması
        mean_lng = sum(point[0] for point in points) / len(points)
        return ref_lat, mean_lng, 0.0

    return weighted_y / total_area / ky, weighted_x / total_area / kx, total_area


def distance_to_line_m(lat: float, lng: float, line: list[tuple[float, float]]) -> float:
    """Noktanın (enlem, boylam) çiftlerinden oluşan bir çizgiye en kısa mesafesi, metre.

    Birkaç kilometrelik ölçekte yerel eş dikdörtgen projeksiyon yeterince hassastır.
    """
    if not line:
        return math.inf
    kx = KM_PER_DEG_LNG_AT_EQUATOR * 1000 * math.cos(math.radians(lat))
    ky = KM_PER_DEG_LAT * 1000
    points = [((point_lng - lng) * kx, (point_lat - lat) * ky) for point_lat, point_lng in line]
    if len(points) == 1:
        return math.hypot(*points[0])

    best = math.inf
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        t = 0.0 if length_sq == 0 else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / length_sq))
        best = min(best, math.hypot(x1 + t * dx, y1 + t * dy))
    return best
