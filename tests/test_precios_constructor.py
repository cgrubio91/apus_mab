"""
Tests de la integración de PRECIOS indexados en el Constructor (_precios_por_insumo).
Puro: sin BD ni IA (la serie de índices se pasa como dict).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.application.use_cases.constructor_apu import _precios_por_insumo


def _refs():
    # Misma descripción → mismo grupo (clave 'cemento'), fechas distintas.
    return [
        {"fecha": "2023-01-10", "insumos": [{"insumo_descripcion": "Cemento gris", "precio_unitario_apu": 800}]},
        {"fecha": "2024-01-10", "insumos": [{"insumo_descripcion": "Cemento gris", "precio_unitario_apu": 900}]},
        {"fecha": "2025-01-10", "insumos": [{"insumo_descripcion": "Cemento gris", "precio_unitario_apu": 1000}]},
    ]


SERIE = {"2023-01": 100.0, "2024-01": 110.0, "2025-01": 121.0}


def test_precios_nominales_sin_serie():
    stats = _precios_por_insumo(_refs(), serie_indice=None)
    grupo = next(s for s in stats if s["clave"] == "cemento")
    assert grupo["indexado"] is False
    assert grupo["n"] == 3
    # Nominales: 800, 900, 1000 → mediana 900
    assert grupo["precio_mediana_hoy"] == 900.0


def test_precios_indexados_a_hoy():
    stats = _precios_por_insumo(_refs(), serie_indice=SERIE)
    grupo = next(s for s in stats if s["clave"] == "cemento")
    assert grupo["indexado"] is True
    # 800@2023→968, 900@2024→990, 1000@2025→1000 → mediana 990
    assert grupo["precio_mediana_hoy"] == 990.0
    assert grupo["min"] == 968.0
    assert grupo["max"] == 1000.0


def test_precios_ignora_invalidos():
    refs = [{"fecha": "2025-01-01", "insumos": [
        {"insumo_descripcion": "Arena", "precio_unitario_apu": 0},
        {"insumo_descripcion": "Arena", "precio_unitario_apu": "x"},
        {"insumo_descripcion": "Arena", "precio_unitario_apu": None},
    ]}]
    assert _precios_por_insumo(refs, serie_indice=SERIE) == []
