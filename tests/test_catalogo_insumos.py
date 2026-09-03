"""
Tests del núcleo puro del catálogo de insumos e indexación (Fase C).
Sin BD ni IA: firma canónica, normalización, estadísticas de precio e
indexación temporal.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.pricing.catalogo_helpers import (
    descripcion_normalizada,
    estadisticas_precio,
    firma_insumo,
    mediana,
)
from src.infrastructure.pricing.indexacion import (
    ajustar_precio,
    indice_para_periodo,
)

# ── firma / normalización ──


def test_firma_colapsa_orden_y_tildes():
    # Mismo conjunto de palabras clave → misma firma (independiente de orden/tildes).
    assert firma_insumo("Cemento gris") == firma_insumo("gris cemento")
    assert firma_insumo("Hormigón reforzado") == firma_insumo("hormigon reforzado")


def test_firma_distingue_insumos_distintos():
    assert firma_insumo("Cemento gris") != firma_insumo("Cemento blanco")


def test_descripcion_normalizada():
    assert descripcion_normalizada("  Árena   de Río ") == "arena de rio"


def test_mediana():
    assert mediana([10, 30, 20]) == 20.0
    assert mediana([10, 20]) == 15.0
    assert mediana([]) is None


# ── estadísticas de precio ──


def test_estadisticas_precio_toma_mas_reciente():
    obs = [
        {"precio": 100, "fecha": "2023-01-01"},
        {"precio": 130, "fecha": "2025-06-01"},
        {"precio": 120, "fecha": "2024-01-01"},
    ]
    st = estadisticas_precio(obs)
    assert st["n"] == 3
    assert st["mediana"] == 120.0
    assert st["min"] == 100.0
    assert st["max"] == 130.0
    assert st["precio_reciente"] == 130.0        # el de 2025
    assert st["fecha_reciente"] == "2025-06-01"


def test_estadisticas_precio_ignora_invalidos_y_vacio():
    assert estadisticas_precio([])["n"] == 0
    st = estadisticas_precio([{"precio": 0}, {"precio": "x"}, {"precio": -5}])
    assert st["n"] == 0


# ── indexación temporal ──


SERIE = {"2023-01": 100.0, "2024-01": 110.0, "2025-01": 121.0}


def test_indice_para_periodo_exacto_y_anterior():
    assert indice_para_periodo(SERIE, "2024-01") == 110.0
    # Sin periodo exacto → usa el último anterior disponible.
    assert indice_para_periodo(SERIE, "2024-07") == 110.0
    assert indice_para_periodo(SERIE, "2022-01") is None


def test_ajustar_precio_lleva_a_pesos_constantes():
    # 100 en 2023-01 (índice 100) llevado a 2025-01 (índice 121) → 121.
    assert ajustar_precio(100, "2023-01-15", "2025-01-20", SERIE) == 121.0


def test_ajustar_precio_sin_indice_no_inventa():
    # Falta índice para la fecha origen → devuelve el precio sin cambio.
    assert ajustar_precio(100, "2019-01-01", "2025-01-01", SERIE) == 100.0
    assert ajustar_precio("no-num", "2023-01", "2025-01", SERIE) is None
