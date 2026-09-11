"""Dış veri kaynaklarından (TKGM, OpenStreetMap) gelen hataların ortak tipleri."""


class NotFound(Exception):
    """Kaynakta istenen kayıt yok (API'de 404'e dönüşür)."""


class UpstreamError(Exception):
    """Dış servise ulaşılamadı ya da beklenmeyen yanıt döndü (API'de 502'ye dönüşür)."""
