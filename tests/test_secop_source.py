"""
Tests unitarios de la fuente SECOP II (funciones puras, sin red ni BD).

Cubren:
  - construcción de parámetros SoQL (búsqueda, filtros, escape de comillas),
  - mapeo tolerante de filas crudas a ReferenciaExterna,
  - el flujo de SecopSource.buscar con un cliente Socrata falso.
"""

import os
import sys
from datetime import date
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.domain.entities.referencia_externa import ReferenciaExterna
from src.infrastructure.scraping.secop_source import (
    SecopSource,
    _parse_decimal,
    _parse_fecha,
    construir_params,
    mapear_fila,
)

# ── construir_params ──


def test_construir_params_basico():
    p = construir_params("box coulvert", limite=50)
    assert p["$q"] == "box coulvert"
    assert p["$limit"] == 50
    assert "DESC" in p["$order"]
    assert "$where" not in p


def test_construir_params_con_ciudad_y_fecha():
    p = construir_params("pavimento", ciudad="Bogotá", desde_fecha="2025-01-01")
    assert "$where" in p
    assert "ciudad" in p["$where"].lower()
    assert "2025-01-01" in p["$where"]
    assert " AND " in p["$where"]


def test_construir_params_escapa_comillas():
    # Una comilla simple en la ciudad no debe romper el literal SoQL.
    p = construir_params("muro", ciudad="O'Higgins")
    assert "O''Higgins" in p["$where"]


def test_construir_params_limita_maximo():
    assert construir_params("x", limite=99999)["$limit"] == 1000


def test_construir_params_keyword_vacio_falla():
    with pytest.raises(ValueError):
        construir_params("   ")


# ── _parse_decimal / _parse_fecha ──


def test_parse_decimal_variantes():
    assert _parse_decimal("1234567") == Decimal("1234567")
    assert _parse_decimal("$ 1.234.567,89") == Decimal("1234567.89")
    assert _parse_decimal("1,234,567.89") == Decimal("1234567.89")
    assert _parse_decimal(None) is None
    assert _parse_decimal("") is None
    assert _parse_decimal("N/A") is None


def test_parse_fecha_variantes():
    assert _parse_fecha("2025-06-15") == date(2025, 6, 15)
    assert _parse_fecha("2025-06-15T00:00:00.000") == date(2025, 6, 15)
    assert _parse_fecha("2025-06-15 10:30:00") == date(2025, 6, 15)
    assert _parse_fecha(None) is None
    assert _parse_fecha("sin-fecha") is None


# ── mapear_fila ──


def _fila_secop_realista() -> dict:
    return {
        "id_contrato": "CO1.PCCNTR.123456",
        "nombre_entidad": "MUNICIPIO DE MEDELLIN",
        "departamento": "Antioquia",
        "ciudad": "Medellín",
        "objeto_del_contrato": "Construcción de box coulvert en concreto reforzado",
        "valor_del_contrato": "1.250.000.000",
        "fecha_de_firma": "2025-03-10T00:00:00.000",
        "proveedor_adjudicado": "Constructora XYZ S.A.S.",
        "urlproceso": {"url": "https://community.secop.gov.co/xyz"},
    }


def test_mapear_fila_completa():
    ref = mapear_fila(_fila_secop_realista())
    assert isinstance(ref, ReferenciaExterna)
    assert ref.fuente == "SECOP II"
    assert ref.granularidad == "contrato"
    assert ref.fuente_id == "CO1.PCCNTR.123456"
    assert ref.ciudad == "Medellín"
    assert ref.entidad == "MUNICIPIO DE MEDELLIN"
    assert ref.precio == Decimal("1250000000")
    assert ref.fecha == date(2025, 3, 10)
    assert ref.url == "https://community.secop.gov.co/xyz"
    assert ref.rendimiento is None  # SECOP open data no trae rendimiento


def test_mapear_fila_nombres_alternativos():
    # Esquema con nombres de columna distintos: el mapeo tolerante debe resolverlos.
    fila = {
        "referencia_del_contrato": "REF-9",
        "descripcion_del_proceso": "Suministro de concreto 3000 psi",
        "cuantia_proceso": "500000",
        "ciudad_entidad": "Cali",
        "fecha_de_firma_del_contrato": "2024-11-01",
    }
    ref = mapear_fila(fila)
    assert ref is not None
    assert ref.descripcion.startswith("Suministro de concreto")
    assert ref.fuente_id == "REF-9"
    assert ref.ciudad == "Cali"
    assert ref.precio == Decimal("500000")


def test_mapear_fila_sin_descripcion_es_none():
    assert mapear_fila({"valor_del_contrato": "100"}) is None


def test_clave_unica_estable():
    ref = mapear_fila(_fila_secop_realista())
    assert ref.clave_unica() == "SECOP II::CO1.PCCNTR.123456"


# ── SecopSource.buscar con cliente falso ──


class _FakeClient:
    def __init__(self, filas):
        self._filas = filas
        self.ultimo_dataset = None
        self.ultimos_params = None

    def query(self, dataset_id, params, max_attempts=3):
        self.ultimo_dataset = dataset_id
        self.ultimos_params = params
        return self._filas


def test_secop_source_buscar_mapea_y_filtra():
    filas = [
        _fila_secop_realista(),
        {"valor_del_contrato": "1"},  # sin descripción → se descarta
    ]
    fake = _FakeClient(filas)
    source = SecopSource(client=fake, dataset_id="test-ds")
    refs = source.buscar("box coulvert", ciudad="Medellín")

    assert len(refs) == 1
    assert refs[0].descripcion.startswith("Construcción de box coulvert")
    assert fake.ultimo_dataset == "test-ds"
    assert fake.ultimos_params["$q"] == "box coulvert"
    assert "Medellín" in fake.ultimos_params["$where"]
