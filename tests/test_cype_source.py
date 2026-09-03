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
