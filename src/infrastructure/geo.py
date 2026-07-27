"""Normalización canónica de nombres de ciudad (Colombia).

Unifica variantes ("BOGOTA", "Bogotá D.C.", ...) a un nombre canónico, y trata
la entidad/ciudad "IDU" (Instituto de Desarrollo Urbano) como Bogotá.

Se usa tanto al insertar APUs (para no reintroducir variantes) como en el
script de migración `scripts/normalizar_ciudades_db.py`.
"""

import re
import unicodedata
from typing import Optional

# Nombre canónico (con tildes/mayúsculas correctas) por clave normalizada.
_CANONICO = {
    "bogota": "Bogotá", "medellin": "Medellín", "cali": "Cali", "barranquilla": "Barranquilla",
    "cartagena": "Cartagena", "bucaramanga": "Bucaramanga", "manizales": "Manizales",
    "pereira": "Pereira", "cucuta": "Cúcuta", "ibague": "Ibagué", "santa marta": "Santa Marta",
    "villavicencio": "Villavicencio", "pasto": "Pasto", "neiva": "Neiva", "armenia": "Armenia",
    "popayan": "Popayán", "monteria": "Montería", "sincelejo": "Sincelejo", "valledupar": "Valledupar",
    "tunja": "Tunja", "riohacha": "Riohacha", "quibdo": "Quibdó", "florencia": "Florencia",
    "yopal": "Yopal", "leticia": "Leticia", "mocoa": "Mocoa", "sonson": "Sonsón",
    "girardot": "Girardot", "duitama": "Duitama", "sogamoso": "Sogamoso", "buenaventura": "Buenaventura",
    "tumaco": "Tumaco", "apartado": "Apartadó", "turbo": "Turbo", "magangue": "Magangué",
    "barrancabermeja": "Barrancabermeja", "palmira": "Palmira", "tulua": "Tuluá", "cartago": "Cartago",
    "zipaquira": "Zipaquirá", "fusagasuga": "Fusagasugá", "facatativa": "Facatativá", "chia": "Chía",
    "soacha": "Soacha", "bello": "Bello", "itagui": "Itagüí", "envigado": "Envigado",
    "rionegro": "Rionegro", "floridablanca": "Floridablanca", "giron": "Girón", "piedecuesta": "Piedecuesta",
    "san andres": "San Andrés", "arauca": "Arauca", "inirida": "Inírida", "mitu": "Mitú",
    "puerto carreno": "Puerto Carreño", "san jose del guaviare": "San José del Guaviare",
    "caucasia": "Caucasia", "la dorada": "La Dorada", "espinal": "Espinal", "honda": "Honda",
    "chiquinquira": "Chiquinquirá",
}

# Claves de varias palabras (para detectar por subcadena).
_CLAVES_MULTI = [k for k in _CANONICO if " " in k]
# Claves de una palabra (para detectar por token).
_CLAVES_UNI = {k for k in _CANONICO if " " not in k}


def _normalizar(texto: Optional[str]) -> str:
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")  # quita tildes
    t = re.sub(r"\bd\.?\s?c\.?\b", " ", t)                        # "D.C."
    t = re.sub(r"distrito\s+(capital|especial|de)?", " ", t)
    t = re.sub(r"[^a-z\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def canonicalizar_ciudad(ciudad: Optional[str], entidad: Optional[str] = None) -> Optional[str]:
    """Devuelve el nombre canónico de la ciudad. IDU (entidad o ciudad) → Bogotá.
    Ciudad vacía → None (se deja como está). Ciudad desconocida → Title Case."""
    ent = _normalizar(entidad)
    ciu = _normalizar(ciudad)

    if ent == "idu" or ciu == "idu":
        return "Bogotá"
    if not ciu:
        return None

    if ciu in _CANONICO:
        return _CANONICO[ciu]
    for clave in _CLAVES_MULTI:
        if clave in ciu:
            return _CANONICO[clave]
    for token in ciu.split(" "):
        if token in _CLAVES_UNI:
            return _CANONICO[token]

    # Desconocida: unifica el uso de mayúsculas conservando el texto original.
    return " ".join(w.capitalize() for w in (ciudad or "").strip().split())
