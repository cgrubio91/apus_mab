"""
Tests unitarios del Constructor de APU (helpers puros, sin BD ni IA).
"""

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.application.use_cases.constructor_apu import (
    _emparejar_filas_cotizacion,
    _fila_desde_propuesta,
    _normalizar_propuesta,
    _parse_fecha,
    _puntaje_recencia,
    _rankear_referencias,
    _aplicar_jerarquia_precios,
    calcular_costo_directo,
    calcular_desglose_aiu,
)

HOY = date(2026, 8, 24)


# ── _parse_fecha ──


def test_parse_fecha_acepta_variantes():
    assert _parse_fecha(None) is None
    assert _parse_fecha("2026-05-01") == date(2026, 5, 1)
    assert _parse_fecha("2026-05-01 10:30:00") == date(2026, 5, 1)
    from datetime import datetime as dt

    assert _parse_fecha(dt(2026, 1, 2, 8, 0)) == date(2026, 1, 2)
    assert _parse_fecha("no-es-fecha") is None


# ── _puntaje_recencia ──


def test_recencia_por_ventanas():
    assert _puntaje_recencia(HOY - timedelta(days=30), HOY) == (1.0, "≤ 6 meses")
    assert _puntaje_recencia(HOY - timedelta(days=200), HOY)[0] == 0.7
    assert _puntaje_recencia(HOY - timedelta(days=400), HOY)[0] == 0.4
    assert _puntaje_recencia(HOY - timedelta(days=800), HOY)[0] == 0.15
    assert _puntaje_recencia(None, HOY)[0] == 0.15


# ── _rankear_referencias ──


def test_rankear_prefiere_misma_ciudad_reciente():
    refs = [
        {"similitud": 0.9, "ciudad": "Cali", "fecha": "2020-01-01", "precio_unitario": 100},
        {"similitud": 0.85, "ciudad": "Medellín", "fecha": HOY.isoformat(), "precio_unitario": 120},
        {"similitud": 0.85, "ciudad": "Medellín", "fecha": "2019-06-01", "precio_unitario": 90},
    ]
    ranked = _rankear_referencias(refs, ciudad="Medellín", hoy=HOY)
    # La referencia de Medellín reciente gana aunque tenga menor similitud que la de Cali.
    assert ranked[0]["ciudad"] == "Medellín"
    assert ranked[0]["recencia"] == "≤ 6 meses"
    assert ranked[0]["ciudad_coincide"] is True
    # Entre las de Medellín, la vieja queda después de la reciente.
    assert ranked.index(next(r for r in ranked if r["fecha"] == "2019-06-01")) > 0
    assert all("_score" in r for r in ranked)


def test_rankear_sin_ciudad_no_premia_coincidencias():
    refs = [
        {"similitud": 0.9, "ciudad": "Bogotá", "fecha": HOY.isoformat()},
        {"similitud": 0.8, "ciudad": "Cali", "fecha": HOY.isoformat()},
    ]
    ranked = _rankear_referencias(refs, ciudad=None, hoy=HOY)
    assert [r["ciudad"] for r in ranked] == ["Bogotá", "Cali"]
    assert all(r["ciudad_coincide"] is False for r in ranked)


def test_rankear_descarta_ciudades_distantes_con_similitud_igual():
    refs = [
        {"similitud": 0.8, "ciudad": "Bogotá", "fecha": HOY.isoformat()},
        {"similitud": 0.8, "ciudad": "Bogotá ", "fecha": HOY.isoformat()},  # espacio final no debe romper
        {"similitud": 0.99, "ciudad": "Pasto", "fecha": "2015-01-01"},
    ]
    ranked = _rankear_referencias(refs, ciudad="bogotá", hoy=HOY)  # case-insensitive
    assert ranked[0]["ciudad"] in ("Bogotá", "Bogotá ")
    assert ranked[-1]["ciudad"] == "Pasto"


# ── _emparejar_filas_cotizacion ──


def test_empareja_por_similitud_y_asigna_una_sola_vez():
    insumos = [
        {"id": 1, "insumo_descripcion": "Cemento gris u"},
        {"id": 2, "insumo_descripcion": "Arena de peña"},
    ]
    filas = [
        {"insumo_descripcion": "CEMENTO GRIS U", "precio_unitario_apu": 35000},
        {"insumo_descripcion": "arena de peña", "precio_unitario": 90000},
        {"insumo_descripcion": "Insumo ajeno total", "precio_unitario": 123},
        {"insumo_descripcion": "cemento gris", "precio_unitario_apu": 999},  # duplicado: no debe re-asignar
    ]
    asignadas, sin_coincidencia = _emparejar_filas_cotizacion(filas, insumos)
    ids = {a["insumo_id"] for a in asignadas}
    assert ids == {1, 2}
    por_insumo = {a["insumo_id"]: a["precio"] for a in asignadas}
    assert por_insumo[1] == 35000  # el mejor par gana (greedy por similitud)
    assert len(sin_coincidencia) == 2  # el ajeno y el duplicado de cemento quedan para revisión
    assert {f["insumo_descripcion"] for f in sin_coincidencia} == {"Insumo ajeno total", "cemento gris"}


def test_empareja_ignora_filas_sin_precio_valido():
    insumos = [{"id": 1, "insumo_descripcion": "Cemento gris u"}]
    filas = [
        {"insumo_descripcion": "CEMENTO GRIS U", "precio_unitario_apu": 0},
        {"insumo_descripcion": "CEMENTO GRIS U", "precio_unitario_apu": None},
    ]
    asignadas, sin_coincidencia = _emparejar_filas_cotizacion(filas, insumos)
    assert asignadas == []
    assert sin_coincidencia == []


def test_fila_desde_propuesta_normaliza_tipo_y_numeros():
    fila = _fila_desde_propuesta(
        {"tipo_insumo": "materiales", "descripcion": " Concreto 3000 psi ", "unidad": "m3",
         "rendimiento": "1.5", "precio": None},
        item="NPC-1", items_descripcion="Pilote", item_unidad="m",
    )
    assert fila["tipo_insumo"] == "Materiales"
    assert fila["insumo_descripcion"] == "Concreto 3000 psi"
    assert fila["rendimiento_insumo"] == 1.5
    assert fila["precio_banco"] is None


def test_fila_desde_propuesta_rechaza_vacias():
    with pytest.raises(ValueError):
        _fila_desde_propuesta({"tipo_insumo": "Materiales", "descripcion": "   "},
                              "NPC-1", "desc", "m")


def test_normalizar_propuesta_sanea_ia():
    data = _normalizar_propuesta({
        "item_descripcion": " Pilote ",
        "unidad": "m",
        "insumos": [
            {"tipo_insumo": "materiales", "descripcion": "Concreto", "rendimiento": "-1", "precio": "100"},
            {"tipo_insumo": "Equipos", "descripcion": "  ", "precio": 1},
            {"descripcion": "Oficial", "tipo_insumo": "Mano de obra", "rendimiento": 0.5, "precio": None},
        ],
        "preguntas": ["¿Diámetro?", "  ", "¿Profundidad?", "extra 4", "extra 5"],
        "notas": " ok ",
    })
    assert data["item_descripcion"] == "Pilote"
    assert len(data["insumos"]) == 2
    assert data["insumos"][0]["tipo_insumo"] == "Materiales"
    assert data["insumos"][0]["rendimiento"] is None  # negativo
    assert data["insumos"][0]["precio"] == 100.0
    assert data["preguntas"] == ["¿Diámetro?", "¿Profundidad?", "extra 4"]


def test_normalizar_propuesta_excluye_aiu_e_indirectos():
    data = _normalizar_propuesta({
        "item_descripcion": "Concreto 1500 PSI",
        "insumos": [
            {"tipo_insumo": "Materiales", "descripcion": "Arena", "rendimiento": 1, "precio": 50000},
            {"tipo_insumo": "Indirectos", "descripcion": "ADMINISTRACION", "rendimiento": 0.2, "precio": 10000},
            {"tipo_insumo": "Indirectos", "descripcion": "IMPREVISTOS", "rendimiento": 0.05, "precio": 2500},
            {"tipo_insumo": "Otro", "descripcion": "Utilidad de obra", "rendimiento": 0.05, "precio": 2500},
            {"tipo_insumo": "Mano de obra", "descripcion": "Oficial", "rendimiento": 0.2, "precio": 30000},
        ],
    })
    descs = [i["descripcion"] for i in data["insumos"]]
    assert descs == ["Arena", "Oficial"]
    assert all(i["tipo_insumo"] != "Indirectos" for i in data["insumos"])


def test_calcular_costo_directo_propuesta_y_bd():
    propuesta = [
        {"precio": 1000, "rendimiento": 2},
        {"precio": None, "rendimiento": 1},
        {"precio": 50, "rendimiento": None},
    ]
    assert calcular_costo_directo(propuesta, exigir_precio=True) == 2050.0
    filas_bd = [
        {"precio_unitario_apu": 10, "rendimiento_insumo": 3},
        {"precio_banco": 100, "rendimiento_insumo": 1},
    ]
    assert calcular_costo_directo(filas_bd, exigir_precio=True) == 30.0
    assert calcular_costo_directo(filas_bd, exigir_precio=False) == 130.0


def test_calcular_desglose_aiu_personalizado():
    cd = 100000.0
    # Default: Adm 15%, Imp 3%, Ut 5%, IVA Ut 19%
    default_aiu = calcular_desglose_aiu(cd)
    assert default_aiu["valores"]["administracion"] == 15000.0
    assert default_aiu["valores"]["imprevistos"] == 3000.0
    assert default_aiu["valores"]["utilidad"] == 5000.0
    assert default_aiu["valores"]["iva_utilidad"] == 950.0
    assert default_aiu["valores"]["total_aiu"] == 23950.0
    assert default_aiu["valores"]["costo_total"] == 123950.0
    assert default_aiu["porcentajes"]["aiu_total_porcentaje"] == 23.95

    # Custom: Adm 18%, Imp 2%, Ut 4%, IVA Ut 19%
    custom_aiu = calcular_desglose_aiu(cd, {
        "administracion": 18,
        "imprevistos": 2,
        "utilidad": 4,
        "iva_utilidad": 19,
    })
    assert custom_aiu["valores"]["administracion"] == 18000.0
    assert custom_aiu["valores"]["imprevistos"] == 2000.0
    assert custom_aiu["valores"]["utilidad"] == 4000.0
    assert custom_aiu["valores"]["iva_utilidad"] == 760.0
    assert custom_aiu["valores"]["total_aiu"] == 24760.0
    assert custom_aiu["valores"]["costo_total"] == 124760.0
    assert custom_aiu["porcentajes"]["aiu_total_porcentaje"] == 24.76


def test_aplicar_jerarquia_precios_prioridad():
    class DummyCype:
        def buscar_referencia_insumo(self, desc, tipo=None, ciudad=None):
            if "acero" in desc.lower():
                return {"precio": 4800, "fuente": "CYPE Colombia - Tarifas Oficiales"}
            return None

    class DummyMateriales:
        def buscar_referencia(self, desc, tipo=None):
            if "arena" in desc.lower():
                return {
                    "precio": 14900,
                    "fuente": "Homecenter · BLF",
                    "fuente_link": "https://www.homecenter.com.co/homecenter-co/product/297066/",
                    "unidad": "Und",
                }
            return None

    class DummyExtRepo:
        def buscar(self, desc, fuente=None, ciudad=None, **kwargs):
            if fuente in ("SECOP II", "SECOP") and "cemento" in desc.lower():
                return [{"precio": 32000, "fuente": "SECOP II", "granularidad": "material"}]
            if fuente in ("SECOP II", "SECOP") and "pintura" in desc.lower():
                return [{"precio": 45000, "fuente": "SECOP II", "url": "https://secop.gov.co/doc/123", "granularidad": "material"}]
            if fuente in ("SECOP II", "SECOP") and "retroexcavadora" in desc.lower():
                # Contrato macro de licitación pública: DEBE SER DESCARTADO
                return [{"precio": 144353664, "fuente": "SECOP II: ANI", "granularidad": "contrato"}]
            return []

    insumos = [
        {"descripcion": "Acero de refuerzo 60ksi", "tipo_insumo": "Materiales"},
        {"descripcion": "Cemento gris tipo 1", "tipo_insumo": "Materiales"},
        {"descripcion": "Arena lavada de río", "tipo_insumo": "Materiales"},
        {"descripcion": "Pintura anticorrosiva", "tipo_insumo": "Materiales"},
        {"descripcion": "Retroexcavadora sobre llantas", "tipo_insumo": "Equipos"},
        {"descripcion": "Insumo exótico desconocido", "tipo_insumo": "Materiales"},
    ]
    precios_ref_banco = {
        "cemento gris": 30000,
    }

    res = _aplicar_jerarquia_precios(
        propuesta={"insumos": insumos},
        solicitud={"ciudad": "Medellín"},
        precios_ref_banco=precios_ref_banco,
        cype_source=DummyCype(),
        referencia_externa_repo=DummyExtRepo(),
        materiales_source=DummyMateriales(),
    )
    ins_res = res["insumos"]

    # 1. Acero debe venir de CYPE (1ª prioridad)
    assert ins_res[0]["precio"] == 4800
    assert "CYPE" in ins_res[0]["fuente"]
    assert "generadordeprecios.info" in ins_res[0]["fuente_link"]

    # 2. Cemento debe venir del Banco de APUs (2ª prioridad, prevalece sobre Homecenter y SECOP)
    assert ins_res[1]["precio"] == 30000
    assert "Banco" in ins_res[1]["fuente"]
    assert ins_res[1]["fuente_link"] == "/banco-apus"

    # 3. Arena lavada debe venir de Homecenter (3ª prioridad: catálogo comercial en vivo)
    assert ins_res[2]["precio"] == 14900
    assert "Homecenter" in ins_res[2]["fuente"]
    assert "297066" in ins_res[2]["fuente_link"]

    # 4. Pintura viene de SECOP II (4ª prioridad: insumo unitario válido)
    assert ins_res[3]["precio"] == 45000
    assert "SECOP II" in ins_res[3]["fuente"]
    assert ins_res[3]["fuente_link"] == "https://secop.gov.co/doc/123"

    # 5. Retroexcavadora: el registro de SECOP es un contrato macro ($144M), DEBE SER DESCARTADO -> queda Pendiente
    assert ins_res[4]["precio"] is None
    assert "Pendiente cotización" in ins_res[4]["fuente"]

    # 6. Insumo exótico no tiene precio en ninguna fuente (5ª prioridad)
    assert ins_res[5]["precio"] is None
    assert "Pendiente cotización" in ins_res[5]["fuente"]

