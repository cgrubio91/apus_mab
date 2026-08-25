"""Helper para extraer ciudad/ubicación del texto de la actividad usando ciudades conocidas del banco."""
import re
import unicodedata

_CIUDADES_BANCO = []
_CIUDADES_ORIGINAL = {}  # norm -> original

def _normalizar(texto: str) -> str:
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    t = t.lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t

def cargar_ciudades_banco():
    global _CIUDADES_BANCO, _CIUDADES_ORIGINAL
    try:
        from src.infrastructure.database.connection import execute_query
        r = execute_query(
            "SELECT DISTINCT ciudad FROM apus WHERE ciudad IS NOT NULL AND TRIM(ciudad) <> ''",
            tuple()
        )
        _CIUDADES_BANCO = []
        _CIUDADES_ORIGINAL = {}
        for row in r:
            ciudad = row['ciudad']
            norm = _normalizar(ciudad)
            _CIUDADES_BANCO.append(norm)
            _CIUDADES_ORIGINAL[norm] = ciudad
        # Variantes comunes
        extras = ["bogota", "bogota d.c.", "medellin", "cali", "barranquilla", "cartagena", "pereira", "manizales", "bucaramanga", "cucuta"]
        for e in extras:
            if e not in _CIUDADES_BANCO:
                _CIUDADES_BANCO.append(e)
        _CIUDADES_BANCO = list(set(_CIUDADES_BANCO))
    except Exception:
        _CIUDADES_BANCO = []

def extraer_ciudad_texto(texto: str) -> str | None:
    if not _CIUDADES_BANCO:
        cargar_ciudades_banco()
    if not texto:
        return None
    texto_norm = _normalizar(texto)
    # Buscar coincidencias (más largas primero para evitar "cal" en "cali")
    for ciudad_norm in sorted(_CIUDADES_BANCO, key=len, reverse=True):
        # Buscar como substring (no word boundary estricto, por puntuación)
        if ciudad_norm in texto_norm:
            # Devolver la versión original con mayúsculas/tildes
            return _CIUDADES_ORIGINAL.get(ciudad_norm, ciudad_norm)
    return None