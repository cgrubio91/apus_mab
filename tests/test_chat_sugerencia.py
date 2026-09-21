"""
Tests de la sugerencia de proveedores del directorio IDU en el chat NL→SQL:
detección de la marca, enrutado fuera del SQL y formateo de la respuesta.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.application.use_cases import chat_assistant as mod


# ── Detección de la marca ──


def test_marca_con_ciudad():
    assert mod._marca_sugerencia_insumo("SUGERIR_PROVEEDORES: pintura anticorrosiva | Bogotá") == (
        "pintura anticorrosiva", "Bogotá")


def test_marca_sin_ciudad():
    assert mod._marca_sugerencia_insumo(
        "SUGERIR_PROVEEDORES: bordillo prefabricado") == ("bordillo prefabricado", None)


def test_marca_case_insensitive_y_fences():
    texto = "```\nsugerir_proveedores: neopreno reforzado\n```"
    assert mod._marca_sugerencia_insumo(texto) == ("neopreno reforzado", None)


def test_marca_con_texto_adyacente():
    texto = ("La actividad se cotiza con:\nSUGERIR_PROVEEDORES: malla electrosoldada | Medellín")
    assert mod._marca_sugerencia_insumo(texto) == ("malla electrosoldada", "Medellín")


def test_sin_marca_no_detecta():
    assert mod._marca_sugerencia_insumo("SELECT * FROM apus LIMIT 5") is None
    assert mod._marca_sugerencia_insumo("") is None
    assert mod._marca_sugerencia_insumo("SUGERIR_PROVEEDORES:   ") is None


# ── Formateo de la respuesta ──


def test_respuesta_con_proveedores_formatea_tabla():
    sugerencia = {
        "grupo": "PINTURAS",
        "insumo_idu": "PINTURA ANTICORROSIVA",
        "precio": None,
        "proveedores": [
            {"nombre": "ALMACENES EASY & CIA", "municipio": "Bogotá", "departamento": "Cundinamarca",
             "telefono": "6017460340", "web_correo": "ventas@easy.co", "contacto": "J. Pérez"},
        ],
    }
    reply, sql_hist, proveedores = mod._redactar_respuesta_sugerencia("pintura anticorrosiva", "Bogotá", sugerencia)
    assert "<table" in reply
    assert "PINTURAS" in reply
    assert "ALMACENES EASY" in reply
    assert "mailto:ventas@easy.co" in reply
    assert "<" not in "ALMACENES EASY & CIA" or "&amp;" in reply  # el & se escapa
    assert sql_hist.startswith("Sugerencia de proveedores")
    assert proveedores == sugerencia["proveedores"]


def test_respuesta_sin_resultado_es_informativa():
    reply, sql_hist, proveedores = mod._redactar_respuesta_sugerencia("artefacto inexistente zzz", None, None)
    assert "No encontré proveedores" in reply
    assert "insumo_referencia_idu" in reply
    assert sql_hist == ""
    assert proveedores == []


def test_fila_proveedor_escapa_html():
    fila = mod._fila_proveedor_html(
        {"nombre": "A&A <HNOS>", "municipio": "Bogotá", "telefono": "<script>",
         "web_correo": "a@b.co", "contacto": "c&d"})
    assert "&lt;HNOS&gt;" in fila
    assert "<script>" not in fila
    assert "&lt;script&gt;" in fila


# ── Flujo completo (sin BD ni IA) ──


def test_procesar_sugerencia_devuelve_resultado_con_etapas(monkeypatch):
    sugerencia = {"grupo": "EQUIPO PESADO", "proveedores": [
        {"nombre": "CENTRALQUIPOS SAS", "municipio": "Bogotá", "telefono": "6012345678"}]}

    def fake_buscar(desc, ciudad=None):
        return sugerencia

    guardadas = []
    monkeypatch.setattr(mod, "_buscar_sugerencia_proveedores", fake_buscar)
    monkeypatch.setattr(mod, "_guardar_conversacion",
                        lambda telefono, msg, sql, reply: guardadas.append((telefono, msg, sql, reply)))

    res = mod._procesar_sugerencia_proveedores(
        ("MOTONIVELADORA 215 HP", None), "¿quién cotiza una motoniveladora?", "123", [], False)
    assert res["reply"].startswith("Para cotizar")
    assert res["sql_query"] is None
    assert res["results"] == sugerencia["proveedores"]
    assert res["suggested_followups"]
    assert any("EQUIPO PESADO" in s for s in res["suggested_followups"])
    assert guardadas and guardadas[0][0] == "123"


def test_procesar_sugerencia_sin_resultado_guarday_responde(monkeypatch):
    monkeypatch.setattr(mod, "_buscar_sugerencia_proveedores", lambda desc, ciudad=None: None)
    monkeypatch.setattr(mod, "_guardar_conversacion", lambda *a, **k: None)
    res = mod._procesar_sugerencia_proveedores(
        ("insumo desconocido", None), "¿quién cotiza insumo desconocido?", "555", [], False)
    assert "No encontré proveedores" in res["reply"]
    assert res["results"] == []