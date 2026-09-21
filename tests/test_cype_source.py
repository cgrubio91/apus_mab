"""
Tests unitarios del adaptador CYPE Colombia y del relleno de precios reales.
"""

import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.scraping.cype_source import CypeSource
from src.application.use_cases.constructor_apu import _rellenar_precios_reales


_DESGLOSE_FAKE = {
    "codigo": "CSZ010",
    "titulo": "Zapata de concreto armado",
    "unidad": "m³",
    "precio_total": Decimal("434745.16"),
    "url": "https://colombia.generadordeprecios.info/CSZ010.html",
    "insumos": [
        {"codigo": "mt26reh302", "tipo_insumo": "Materiales", "descripcion": "Tornillo de acero de 6 mm",
         "unidad": "Ud", "rendimiento": Decimal("2"), "precio": Decimal("136.77")},
        {"codigo": "mt07aco060a", "tipo_insumo": "Materiales", "descripcion": "Acero en barras corrugadas, Grado 60",
         "unidad": "kg", "rendimiento": Decimal("51"), "precio": Decimal("3149.64")},
        {"codigo": "mo043", "tipo_insumo": "Mano de obra", "descripcion": "Oficial 1ª armador de concreto.",
         "unidad": "h", "rendimiento": Decimal("0.174"), "precio": Decimal("41092.96")},
        {"codigo": "", "tipo_insumo": "Herramienta", "descripcion": "Herramienta menor",
         "unidad": "%", "rendimiento": Decimal("2"), "precio": Decimal("4111866.54")},
    ],
}


def _cype_mockeado(monkeypatch, desglose=_DESGLOSE_FAKE, resultados=None):
    """CypeSource que no toca la red: devuelve un desglose fijo."""
    src = CypeSource()
    items = resultados if resultados is not None else [{"codigo": "CSZ010", "titulo": "Zapata",
                                                        "url": _DESGLOSE_FAKE["url"]}]
    monkeypatch.setattr(src, "buscar", lambda q, limite=5: items)
    monkeypatch.setattr(src, "extraer_desglose", lambda url: desglose)
    return src


def test_cotiza_en_vivo_y_devuelve_el_enlace_del_soporte(monkeypatch):
    """El precio sale del desglose descargado y trae la URL de la que se extrajo."""
    src = _cype_mockeado(monkeypatch)

    ref = src.buscar_referencia_insumo("Acero de refuerzo figurado", tipo_insumo="Materiales")
    assert ref is not None
    assert ref["precio"] == Decimal("3149.64")      # barras corrugadas, no el tornillo
    assert ref["unidad"] == "kg"
    assert "mt07aco060a" in ref["fuente"]
    assert ref["url"] == _DESGLOSE_FAKE["url"]      # soporte verificable, no la portada


def test_no_inventa_precio_cuando_cype_no_responde(monkeypatch):
    """Sin respuesta de CYPE no se devuelve ningún precio: la cascada sigue al banco."""
    src = _cype_mockeado(monkeypatch, resultados=[])
    assert src.buscar_referencia_insumo("Concreto 3000 PSI", tipo_insumo="Materiales") is None


def test_descarta_insumo_de_otro_material(monkeypatch):
    """Un insumo que solo comparte una palabra no debe adoptarse como precio."""
    grama = dict(_DESGLOSE_FAKE, insumos=[
        {"codigo": "mt47cit230b", "tipo_insumo": "Materiales",
         "descripcion": "Grama sintética sobre base de concreto", "unidad": "m²",
         "rendimiento": Decimal("1"), "precio": Decimal("57186.87")},
    ])
    src = _cype_mockeado(monkeypatch, desglose=grama)
    assert src.buscar_referencia_insumo("Concreto 3000 PSI", tipo_insumo="Materiales") is None


def test_descarta_herramienta_menor_porcentual(monkeypatch):
    """La herramienta menor de CYPE es un % sobre la mano de obra, no un precio unitario."""
    src = _cype_mockeado(monkeypatch)
    assert src.buscar_referencia_insumo("Herramienta menor", tipo_insumo="Equipos") is None


def test_clasifica_insumos_por_prefijo_de_codigo():
    """mo/mq/mt determinan la categoría; antes la mano de obra caía en 'Materiales'."""
    from src.infrastructure.scraping.cype_source import clasificar_por_codigo

    assert clasificar_por_codigo("mo043") == "Mano de obra"
    assert clasificar_por_codigo("mq06pym020") == "Equipos"
    assert clasificar_por_codigo("mt07aco060a") == "Materiales"


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


def test_rellenar_precios_reales_completa_insumos_vacios(monkeypatch):
    """CYPE cotiza lo que encuentra en vivo; lo que no, se deja sin precio para que la
    cascada siga al banco de APUs en lugar de inventar una cifra."""
    import src.infrastructure.scraping.cype_source as cype_mod

    fake = _cype_mockeado(monkeypatch)
    monkeypatch.setattr(cype_mod, "CypeSource", lambda *a, **kw: fake)

    propuesta = {
        "insumos": [
            {"tipo_insumo": "Mano de obra", "descripcion": "Oficial", "unidad": "h", "precio": None, "fuente": None},
            {"tipo_insumo": "Materiales", "descripcion": "Membrana geotextil no tejida", "unidad": "m2", "precio": None, "fuente": None},
            {"tipo_insumo": "Equipos", "descripcion": "Vibrador de concreto", "unidad": "h", "precio": 11000.0, "fuente": "Banco INVIAS"},
        ]
    }
    insumos = _rellenar_precios_reales(propuesta, ciudad="Bogota")["insumos"]

    # Oficial sí está en el desglose de CYPE.
    assert insumos[0]["precio"] == 41092.96
    assert "CYPE" in insumos[0]["fuente"]
    assert insumos[0]["fuente_link"].startswith("https://colombia.generadordeprecios.info/")

    # Lo que CYPE no cubre no se le atribuye a CYPE: lo resuelve (o no) el resto de la
    # cascada —banco de APUs, catálogo comercial, SECOP—, nunca un precio inventado aquí.
    assert "CYPE" not in (insumos[1].get("fuente") or "")

    # Un precio ya resuelto por el banco se conserva intacto.
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

