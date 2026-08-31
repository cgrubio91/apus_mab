"""
Tests de la fuente DANE y la indexación de observaciones.
Puro: sin red ni BD.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.pricing.indexacion import indexar_observaciones
from src.infrastructure.scraping.dane_source import (
    DaneSource,
    mapear_fila_indice,
    normalizar_periodo,
)

# ── normalizar_periodo ──


def test_normalizar_periodo_formatos():
    assert normalizar_periodo("2025-06") == "2025-06"
    assert normalizar_periodo("2025-06-01") == "2025-06"
    assert normalizar_periodo("202506") == "2025-06"
    assert normalizar_periodo("junio 2025") == "2025-06"
    assert normalizar_periodo("junio", anio="2025") == "2025-06"
    assert normalizar_periodo("2025") is None       # solo año, sin mes
    assert normalizar_periodo("") is None


# ── mapear_fila_indice ──


def test_mapear_fila_indice_autodetecta():
    assert mapear_fila_indice({"periodo": "2025-06", "indice": "121,5"}) == ("2025-06", 121.5)
    assert mapear_fila_indice({"mes": "junio", "anio": "2025", "valor": "121.5"}) == ("2025-06", 121.5)


def test_mapear_fila_indice_columnas_explicitas():
    fila = {"col_periodo": "2024-01", "col_valor": "110"}
    assert mapear_fila_indice(fila, campo_periodo="col_periodo", campo_valor="col_valor") == ("2024-01", 110.0)


def test_mapear_fila_indice_invalida():
    assert mapear_fila_indice({"periodo": "2025", "indice": "x"}) is None
    assert mapear_fila_indice({"indice": "100"}) is None


# ── indexar_observaciones ──


SERIE = {"2023-01": 100.0, "2024-01": 110.0, "2025-01": 121.0}


def test_indexar_observaciones_a_periodo_mas_reciente():
    obs = [
        {"precio": 100, "fecha": "2023-01-15"},   # ×121/100 = 121
        {"precio": 200, "fecha": "2025-01-10"},   # ya en destino → 200
    ]
    idx = indexar_observaciones(obs, SERIE)
    assert idx[0]["precio"] == 121.0
    assert idx[1]["precio"] == 200.0
    # No muta el original.
    assert obs[0]["precio"] == 100


def test_indexar_observaciones_sin_indice_deja_nominal():
    obs = [{"precio": 100, "fecha": "2019-01-01"}]  # fuera de la serie
    idx = indexar_observaciones(obs, SERIE)
    assert idx[0]["precio"] == 100.0


# ── DaneSource con cliente falso ──


class _FakeClient:
    def __init__(self, filas):
        self._filas = filas

    def query_paginado(self, dataset_id, params, max_total=5000):
        return self._filas


def test_dane_source_obtener_serie_dedup_por_periodo():
    filas = [
        {"periodo": "2024-01", "indice": "110"},
        {"periodo": "2025-01", "indice": "121"},
        {"periodo": "2025-01", "indice": "121.5"},  # mismo periodo → gana el último
        {"periodo": "basura", "indice": "x"},        # inválida → se ignora
    ]
    src = DaneSource(client=_FakeClient(filas))
    serie = src.obtener_serie("ds-test")
    assert serie == [("2024-01", 110.0), ("2025-01", 121.5)]
