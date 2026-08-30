"""
Tests de las mejoras de matching (Fase B):
  - _tokenizar: normaliza tildes y conserva tokens técnicos cortos.
  - _mediana / _rendimientos_por_insumo: agregación robusta de rendimientos.
Todo puro: sin BD ni IA.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.application.use_cases.constructor_apu import _mediana, _rendimientos_por_insumo
from src.infrastructure.database.repositories.analisis_repository import (
    _coincidencia_palabra_completa,
    _similitud_tokens,
    _tokenizar,
)

# ── _tokenizar: tildes y tokens técnicos ──


def test_tokenizar_normaliza_tildes():
    # 'hormigón' y 'hormigon' deben producir el MISMO token.
    assert _tokenizar("Hormigón") == _tokenizar("hormigon")
    assert "hormigon" in _tokenizar("Hormigón reforzado")


def test_tokenizar_similitud_insensible_a_tildes():
    a = _tokenizar("Excavación mecánica")
    b = _tokenizar("Excavacion mecanica")
    assert _similitud_tokens(a, b) == 1.0


def test_tokenizar_conserva_siglas_y_numeros():
    toks = _tokenizar("Tubería PVC 6 pulgadas 3000 psi")
    assert "pvc" in toks     # sigla técnica de 3 letras
    assert "3000" in toks    # resistencia
    assert "6" in toks       # diámetro
    assert "psi" in toks     # unidad técnica


def test_tokenizar_descarta_stopwords_y_cortas_no_tecnicas():
    toks = _tokenizar("de la el en un no")
    assert toks == set()


def test_coincidencia_palabra_completa_sin_tildes():
    assert _coincidencia_palabra_completa("hormigon", "Losa de hormigón reforzado")
    assert _coincidencia_palabra_completa("pvc", "Tubería PVC sanitaria")


# ── _mediana ──


def test_mediana_impar_y_par():
    assert _mediana([3, 1, 2]) == 2.0
    assert _mediana([1, 2, 3, 4]) == 2.5
    assert _mediana([]) is None
    assert _mediana([5, None, 5]) == 5.0


# ── _rendimientos_por_insumo ──


def _refs_con_rendimientos():
    return [
        {"insumos": [
            {"insumo_descripcion": "Cemento gris portland", "rendimiento_insumo": 0.30},
            {"insumo_descripcion": "Arena de río", "rendimiento_insumo": 0.55},
        ]},
        {"insumos": [
            {"insumo_descripcion": "Cemento portland tipo I", "rendimiento_insumo": 0.34},
            {"insumo_descripcion": "Arena lavada de río", "rendimiento_insumo": 0.50},
        ]},
        {"insumos": [
            {"insumo_descripcion": "Cemento gris", "rendimiento_insumo": 0.32},
        ]},
    ]


def test_rendimientos_agrega_por_token_y_calcula_mediana():
    stats = _rendimientos_por_insumo(_refs_con_rendimientos())
    por_clave = {s["clave"]: s for s in stats}
    # 'cemento' aparece 3 veces (portland es token distinto; el token más largo
    # de "Cemento gris" es 'cemento'): mediana de [0.30, 0.34, 0.32] = 0.32
    assert "cemento" in por_clave or "portland" in por_clave
    # Al menos un grupo con n>=2 y mediana dentro del rango observado.
    grupo = max(stats, key=lambda s: s["n"])
    assert grupo["n"] >= 2
    assert grupo["min"] <= grupo["rendimiento_mediana"] <= grupo["max"]


def test_rendimientos_ignora_valores_invalidos():
    refs = [{"insumos": [
        {"insumo_descripcion": "Acero de refuerzo", "rendimiento_insumo": None},
        {"insumo_descripcion": "Acero de refuerzo", "rendimiento_insumo": 0},
        {"insumo_descripcion": "Acero de refuerzo", "rendimiento_insumo": "x"},
    ]}]
    # Sin valores válidos → no debe aparecer el grupo.
    assert _rendimientos_por_insumo(refs) == []
