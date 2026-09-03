"""
Tests unitarios del adaptador CYPE Colombia y del relleno de precios reales.
"""

import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.scraping.cype_source import CypeSource, TARIFAS_MANO_DE_OBRA_CYPE
from src.application.use_cases.constructor_apu import _rellenar_precios_reales


def test_tarifas_mano_de_obra_cype():
    src = CypeSource()
    cuadrilla = src.buscar_referencia_insumo("Cuadrilla de construcción (Oficial + Ayudante)", tipo_insumo="Mano de obra")
    assert cuadrilla is not None
    assert cuadrilla["precio"] == TARIFAS_MANO_DE_OBRA_CYPE["cuadrilla"]
    assert cuadrilla["unidad"] == "h"
    assert "CYPE Colombia" in cuadrilla["fuente"]


def test_referencia_materiales_cype():
    src = CypeSource()
    # Concreto
    concreto = src.buscar_referencia_insumo("Concreto 3000 PSI", tipo_insumo="Materiales")
    assert concreto is not None
    assert concreto["precio"] > Decimal("600000")
    assert concreto["unidad"] == "m3"

    # Acero
    acero = src.buscar_referencia_insumo("Acero de refuerzo figurado y colocado", tipo_insumo="Materiales")
    assert acero is not None
    assert acero["precio"] > Decimal("3000")
    assert acero["unidad"] == "kg"

    # Madera
    madera = src.buscar_referencia_insumo("Madera para encofrado (tablas, listones)", tipo_insumo="Materiales")
    assert madera is not None
    assert madera["precio"] > Decimal("0")


def test_parsear_html_desglose_cype():
    src = CypeSource()
    html_sample = """
    <html><body>
    <table>
        <tr><td>CSZ010 | Zapata de cimentación de concreto armado</td></tr>
    </table>
    <table>
        <tr><td>Precio $ 707.791,40 m³</td></tr>
    </table>
    <table>
        <tr><td>Código</td><td>Unidad</td><td>Descripción</td><td>Cantidad</td><td>Valor unitario</td><td>Valor parcial</td></tr>
        <tr><td colspan="6">Materiales</td></tr>
        <tr><td>mt07aco060a</td><td>kg</td><td>Acero en barras corrugadas</td><td>51,000</td><td>3.149,64</td><td>160.631,64</td></tr>
        <tr><td colspan="6">Mano de obra</td></tr>
        <tr><td>mo043</td><td>h</td><td>Oficial 1ª armador</td><td>0,174</td><td>41.092,96</td><td>7.150,18</td></tr>
    </table>
    </body></html>
    """
    desglose = src._parsear_html_desglose(html_sample, url="http://test.com")
    assert desglose is not None
    assert desglose["codigo"] == "CSZ010"
    assert desglose["unidad"] == "m³"
    assert desglose["precio_total"] == Decimal("707791.40")
    assert len(desglose["insumos"]) == 2
    assert desglose["insumos"][0]["descripcion"] == "Acero en barras corrugadas"
    assert desglose["insumos"][0]["precio"] == Decimal("3149.64")
    assert desglose["insumos"][1]["descripcion"] == "Oficial 1ª armador"
    assert desglose["insumos"][1]["precio"] == Decimal("41092.96")


def test_rellenar_precios_reales_completa_insumos_vacios():
    propuesta = {
        "insumos": [
            {"tipo_insumo": "Materiales", "descripcion": "Concreto 3000 PSI", "unidad": "m3", "precio": None, "fuente": "Sin referencia"},
            {"tipo_insumo": "Mano de obra", "descripcion": "Cuadrilla Oficial + Ayudante", "unidad": "h", "precio": None, "fuente": None},
            {"tipo_insumo": "Equipos", "descripcion": "Vibrador de concreto", "unidad": "h", "precio": 11000.0, "fuente": "Banco INVIAS"},
        ]
    }
    resultado = _rellenar_precios_reales(propuesta, ciudad="Bogota")
    insumos = resultado["insumos"]
    
    # Concreto debe tener precio
    assert insumos[0]["precio"] is not None
    assert insumos[0]["precio"] > 0
    assert "CYPE" in insumos[0]["fuente"]

    # Cuadrilla debe tener precio
    assert insumos[1]["precio"] is not None
    assert insumos[1]["precio"] > 0
    assert "CYPE" in insumos[1]["fuente"]

    # Vibrador debe conservar su precio original del banco
    assert insumos[2]["precio"] == 11000.0
    assert insumos[2]["fuente"] == "Banco INVIAS"


def test_ingerir_cype_con_mock(monkeypatch):
    from src.application.use_cases.ingesta_referencias import ingerir_cype

    class MockCypeSource:
        def buscar(self, query, limite=5):
            return [{"codigo": "CSZ010", "titulo": "Zapata de concreto", "url": "https://cype.com/zapata"}]

        def extraer_desglose(self, url):
            return {
                "codigo": "CSZ010",
                "titulo": "Zapata de concreto",
                "unidad": "m3",
                "precio_total": Decimal("700000"),
                "url": url,
                "insumos": [
                    {
                        "codigo": "mt01",
                        "descripcion": "Acero corrugado",
                        "unidad": "kg",
                        "precio": Decimal("3200"),
                        "rendimiento": Decimal("50"),
                    }
                ],
            }

    # Mock del repo para no necesitar BD
    guardadas = []
    monkeypatch.setattr(
        "src.infrastructure.database.repositories.referencia_externa_repository.referencia_externa_repo.upsert_muchas",
        lambda refs: guardadas.extend(refs) or {"afectadas": len(refs)},
    )

    res = ingerir_cype("zapata", limite=1, source=MockCypeSource())
    assert res["success"] is True
    assert res["referencias_traidas"] == 1
    assert len(guardadas) == 1
    assert guardadas[0].fuente == "CYPE Colombia"
    assert guardadas[0].descripcion == "Acero corrugado"
    assert guardadas[0].precio == Decimal("3200")


def test_ingerir_homecenter_con_mock(monkeypatch):
    from src.application.use_cases.ingesta_referencias import ingerir_homecenter

    class MockCatalogoMaterialesSource:
        def buscar_material(self, query, limite=5):
            return [
                {
                    "nombre": "Cemento Gris Uso General 50kg",
                    "marca": "Argos",
                    "precio": Decimal("34900"),
                    "unidad": "bto",
                }
            ]

    guardadas = []
    monkeypatch.setattr(
        "src.infrastructure.database.repositories.referencia_externa_repository.referencia_externa_repo.upsert_muchas",
        lambda refs: guardadas.extend(refs) or {"afectadas": len(refs)},
    )

    res = ingerir_homecenter("cemento", limite=1, source=MockCatalogoMaterialesSource())
    assert res["success"] is True
    assert res["referencias_traidas"] == 1
    assert len(guardadas) == 1
    assert guardadas[0].fuente == "Constructor Homecenter"
    assert guardadas[0].precio == Decimal("34900")
    assert guardadas[0].granularidad == "material"

