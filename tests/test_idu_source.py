"""
Tests de la fuente documental IDU (mapeo puro + flujo con dobles).
Sin red ni IA: la descarga y la extracción se inyectan.
"""

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.domain.entities.referencia_externa import ReferenciaExterna
from src.infrastructure.scraping.documental_source import mapear_fila_extraida
from src.infrastructure.scraping.idu_source import IduSource, urls_semilla
from src.infrastructure.scraping.invias_source import InviasSource

# ── mapear_fila_extraida ──


def test_mapea_insumo_con_rendimiento():
    fila = {
        "insumo_descripcion": "Cemento gris portland tipo I",
        "insumo_unidad": "kg",
        "tipo_insumo": "Materiales",
        "rendimiento_insumo": 0.34,
        "precio_unitario_apu": 850.0,
        "codigo_insumo": "MAT-001",
    }
    ref = mapear_fila_extraida(fila, "IDU", ciudad_defecto="Bogotá", fecha_defecto="2025-01-01")
    assert isinstance(ref, ReferenciaExterna)
    assert ref.fuente == "IDU"
    assert ref.granularidad == "insumo"
    assert ref.descripcion.startswith("Cemento gris")
    assert ref.precio == Decimal("850.0")
    assert ref.rendimiento == Decimal("0.34")
    assert ref.unidad == "kg"
    assert ref.ciudad == "Bogotá"
    assert ref.fecha.isoformat() == "2025-01-01"


def test_mapea_material_sin_rendimiento_usa_precio_unitario():
    fila = {"items_descripcion": "Arena de peña", "item_unidad": "m3", "precio_unitario": 62000}
    ref = mapear_fila_extraida(fila, "IDU", ciudad_defecto="Bogotá")
    assert ref.granularidad == "material"
    assert ref.precio == Decimal("62000")
    assert ref.ciudad == "Bogotá"
    assert ref.rendimiento is None


def test_ciudad_de_la_fila_gana_al_defecto():
    fila = {"insumo_descripcion": "Concreto 3000 psi", "precio_unitario_apu": 500000, "ciudad": "Soacha"}
    ref = mapear_fila_extraida(fila, "IDU", ciudad_defecto="Bogotá")
    assert ref.ciudad == "Soacha"


def test_fila_sin_descripcion_es_none():
    assert mapear_fila_extraida({"precio_unitario_apu": 100}, "IDU") is None


# ── urls_semilla ──


def test_urls_semilla_parsea_env(monkeypatch):
    monkeypatch.setenv("IDU_URLS_SEED", "http://a.com/x.pdf, http://b.com/y.xlsx")
    urls = urls_semilla()
    assert urls == ["http://a.com/x.pdf", "http://b.com/y.xlsx"]


def test_urls_semilla_vacia(monkeypatch):
    monkeypatch.delenv("IDU_URLS_SEED", raising=False)
    assert urls_semilla() == []


# ── IduSource: resolución de URLs y flujo con dobles ──


def test_resolver_urls_combina_y_deduplica(monkeypatch):
    monkeypatch.setenv("IDU_URLS_SEED", "http://seed.com/a.pdf")
    src = IduSource()
    urls = src.resolver_urls(["http://explicita.com/b.pdf", "http://seed.com/a.pdf"])
    assert urls == ["http://explicita.com/b.pdf", "http://seed.com/a.pdf"]


def test_ingerir_documento_flujo_con_dobles(tmp_path):
    # Doble de descarga: crea un archivo local; doble de extracción: filas fijas.
    archivo = tmp_path / "lista_precios.xlsx"
    archivo.write_text("dummy")

    def fake_descargar(url):
        return str(archivo)

    def fake_extraer(ruta, filename):
        return [
            {"insumo_descripcion": "Acero de refuerzo 60000 psi", "insumo_unidad": "kg",
             "rendimiento_insumo": 1.05, "precio_unitario_apu": 4200},
            {"insumo_descripcion": "", "precio_unitario_apu": 1},  # sin descripción → se descarta
        ]

    src = IduSource(descargar=fake_descargar, extraer=fake_extraer)
    refs = src.ingerir_documento("http://idu.gov.co/lista_precios.xlsx", fecha="2025-06-01")

    assert len(refs) == 1
    assert refs[0].fuente == "IDU"
    assert refs[0].ciudad == "Bogotá"          # ciudad por defecto de IDU
    assert refs[0].precio == Decimal("4200")
    assert refs[0].rendimiento == Decimal("1.05")
    assert refs[0].fuente_id == "http://idu.gov.co/lista_precios.xlsx"
    # El temporal se borra al terminar (aquí es tmp_path, no se toca el real).
    assert not archivo.exists()


# ── INVÍAS: mismo pipeline, sin ciudad por defecto ──


def test_invias_no_fuerza_ciudad(tmp_path, monkeypatch):
    monkeypatch.delenv("INVIAS_URLS_SEED", raising=False)
    archivo = tmp_path / "precios_regional.pdf"
    archivo.write_text("dummy")

    def fake_extraer(ruta, filename):
        return [{"insumo_descripcion": "Base granular", "insumo_unidad": "m3",
                 "rendimiento_insumo": 1.0, "precio_unitario_apu": 90000, "ciudad": "Villavicencio"}]

    src = InviasSource(descargar=lambda url: str(archivo), extraer=fake_extraer)
    refs = src.ingerir_documento("http://invias.gov.co/precios_regional.pdf")
    assert len(refs) == 1
    assert refs[0].fuente == "INVÍAS"
    assert refs[0].ciudad == "Villavicencio"   # viene de la fila, no de un defecto
