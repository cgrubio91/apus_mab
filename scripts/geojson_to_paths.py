"""Convierte el GeoJSON de Colombia (departamentos) a rutas SVG proyectadas.

Genera  frontend/public/geo/colombia-paths.json  con:
  { "w", "h", "bounds": [minLon, minLat, maxLon, maxLat], "paths": [ "M.. L.. Z", ... ] }

El frontend dibuja esos paths y proyecta las burbujas de ciudad con los MISMOS
límites, así todo queda alineado. Se reduce la precisión para bajar el tamaño.
"""

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "frontend" / "public" / "geo" / "colombia.geo.json"
SALIDA = RAIZ / "frontend" / "public" / "geo" / "colombia-paths.json"

W = 340
PAD = 8


def _coords_de(geom):
    """Devuelve lista de anillos [[ [lon,lat], ... ], ...] para Polygon/MultiPolygon."""
    t = geom.get("type")
    c = geom.get("coordinates", [])
    if t == "Polygon":
        return c
    if t == "MultiPolygon":
        anillos = []
        for poly in c:
            anillos.extend(poly)
        return anillos
    return []


def main():
    obj = json.loads(ENTRADA.read_text(encoding="utf-8"))
    feats = obj.get("features", [])

    # Límites del territorio CONTINENTAL (se ignora San Andrés/Providencia, lon < -79.5,
    # para que el continente llene el mapa; la isla queda fuera del lienzo y se recorta).
    MAINLAND_MIN_LON = -79.5
    min_lon = min_lat = 1e9
    max_lon = max_lat = -1e9
    for f in feats:
        for anillo in _coords_de(f.get("geometry", {})):
            for lon, lat in anillo:
                if lon < MAINLAND_MIN_LON:
                    continue
                min_lon = min(min_lon, lon); max_lon = max(max_lon, lon)
                min_lat = min(min_lat, lat); max_lat = max(max_lat, lat)

    span_lon = max_lon - min_lon
    span_lat = max_lat - min_lat
    H = round(W * span_lat / span_lon)

    def proj(lon, lat):
        x = PAD + (lon - min_lon) / span_lon * (W - 2 * PAD)
        y = PAD + (max_lat - lat) / span_lat * (H - 2 * PAD)
        return round(x, 1), round(y, 1)

    paths = []
    for f in feats:
        subpaths = []
        for anillo in _coords_de(f.get("geometry", {})):
            pts = []
            prev = None
            for lon, lat in anillo:
                p = proj(lon, lat)
                if p != prev:  # dedup consecutivos
                    pts.append(p)
                    prev = p
            if len(pts) >= 3:
                d = "M" + " L".join(f"{x} {y}" for x, y in pts) + " Z"
                subpaths.append(d)
        if subpaths:
            paths.append(" ".join(subpaths))

    salida = {
        "w": W, "h": H,
        "bounds": [round(min_lon, 4), round(min_lat, 4), round(max_lon, 4), round(max_lat, 4)],
        "paths": paths,
    }
    SALIDA.write_text(json.dumps(salida, separators=(",", ":")), encoding="utf-8")
    print(f"Departamentos: {len(paths)} | viewBox {W}x{H} | {SALIDA.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
