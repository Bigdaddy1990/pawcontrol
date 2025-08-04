"""Hilfsfunktionen für GPS-Features von Paw Control."""

def is_valid_gps_coords(lat, lon):
    """Prüft, ob Latitude und Longitude gültig sind."""
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180

def format_gps_coords(lat, lon):
    """Formatierte Ausgabe für Koordinaten."""
    if not is_valid_gps_coords(lat, lon):
        return "Ungültig"
    return f"{lat:.5f}, {lon:.5f}"
