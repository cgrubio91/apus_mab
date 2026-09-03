"""
Tests unitarios de la fuente ANI (funciones puras, sin red ni BD).
"""

import os
import sys
from datetime import date
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.scraping.ani_source import (
    AniSource,
    _parse_decimal,
    _parse_fecha,
    construir_params,
    mapear_fila,
)


def test_construir_params_basico():
    p = construir_params("concesion vial", limite=50)
    assert p["$q"] == "concesion vial"
    assert p["$limit"] == 50
    assert "$where" not in p


def test_construir_params_con_ciudad():
    p = construir_params("autopista", ciudad="Medellín")
    assert "$where" in p
    assert "medellín" in p["$where"].lower()


def test_construir_params_keyword_vacio():
    with pytest.raises(ValueError):
        construir_params("   ")


def test_mapear_fila_completa():
    row = {
        "objeto_del_proyecto": "Construcción y operación de la Autopista al Mar 1",
        "numero_contrato": "ANI-APP-001-2022",
        "valor_inversion": "2.500.000.000,00",
        "municipio": "Santa Fe de Antioquia",
        "departamento": "Antioquia",
        "concesionario": "Devimar S.A.S.",
        "fecha_firma_contrato": "2022-05-15T00:00:00.000",
        "enlace": "https://ani.gov.co/proyectos/mar-1",
    }
    ref = mapear_fila(row)
    assert ref is not None
    assert ref.fuente == "ANI"
    assert ref.fuente_id == "ANI-APP-001-2022"
    assert "Autopista al Mar 1" in ref.descripcion
    assert ref.precio == Decimal("2500000000.00")
    assert ref.ciudad == "Santa Fe de Antioquia"
    assert ref.departamento == "Antioquia"
    assert ref.proveedor == "Devimar S.A.S."
    assert ref.fecha == date(2022, 5, 15)
    assert ref.url == "https://ani.gov.co/proyectos/mar-1"
    assert ref.granularidad == "contrato"


def test_mapear_fila_sin_descripcion():
    row = {"valor_inversion": "1000000"}
    assert mapear_fila(row) is None


def test_ani_source_buscar_mock():
    class MockSocrataClient:
        def query(self, dataset_id, params):
            return [
                {
                    "nombre_proyecto": "Malla Vial del Meta",
                    "codigo_proyecto": "ANI-002",
                    "valor_total": "1800000000",
                    "municipio": "Villavicencio",
                    "concesionario": "Concesión Vial de los Llanos",
                    "fecha_inicio": "2021-03-10",
                }
            ]

    src = AniSource(client=MockSocrataClient())
    refs = src.buscar("malla vial", limite=10)
    assert len(refs) == 1
    assert refs[0].descripcion == "Malla Vial del Meta"
    assert refs[0].fuente_id == "ANI-002"
    assert refs[0].precio == Decimal("1800000000")
    assert refs[0].ciudad == "Villavicencio"
