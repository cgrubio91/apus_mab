"""
Tests del directorio de proveedores del IDU y del Banco de Precios de Referencia:
emparejamiento insumo → grupo, sugerencia de proveedores y uso del precio oficial.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.application.use_cases.constructor_propuesta import _aplicar_jerarquia_precios
from src.infrastructure.database.repositories.proveedor_repository import (
    ProveedorRepository,
    _raiz,
    _tokens,
)


class _RepoFalso(ProveedorRepository):
    """Repositorio con el BPR y los grupos en memoria, sin tocar la BD."""

    BPR = [
        {"codigo": "6116", "grupo": "BORDILLOS Y LOSETAS", "unidad": "UN", "precio": 46992,
         "nombre": "BORDILLO PREFABRICADO A80 (800X200X350MM)"},
        {"codigo": "6013", "grupo": "EQUIPO PESADO", "unidad": "HR", "precio": 327250,
         "nombre": "MOTONIVELADORA - MASA DE 16 A 18 TONELADAS"},
        {"codigo": "9001", "grupo": "ESTRUCTURAS EN ACERO", "unidad": "KG", "precio": 12000,
         "nombre": "ACERO ESTRUCTURAL A709 (INCLUYE PINTURA ANTICORROSIVA)"},
    ]
    GRUPOS = ["BORDILLOS Y LOSETAS", "EQUIPO PESADO", "ESTRUCTURAS EN ACERO", "PINTURAS"]
    PROVEEDORES = {
        "BORDILLOS Y LOSETAS": [{"nombre": "INVERSIONES TJ", "municipio": "Bogotá",
                                 "telefono": "3143941329", "web_correo": None, "contacto": None}],
        "EQUIPO PESADO": [{"nombre": "CENTRALQUIPOS SAS", "municipio": "Bogotá",
                           "telefono": "6012345678", "web_correo": None, "contacto": None}],
        "PINTURAS": [{"nombre": "ALMACENES EASY", "municipio": "Bogotá",
                      "telefono": "6017460340", "web_correo": None, "contacto": None}],
        "ESTRUCTURAS EN ACERO": [{"nombre": "ACEROS XYZ", "municipio": "Medellín",
                                  "telefono": "6041112222", "web_correo": None, "contacto": None}],
    }

    def _consultar_bpr(self, ancla):
        return [f for f in self.BPR if ancla in f["nombre"].lower()]

    def _consultar_grupos(self):
        return [{"grupo": g} for g in self.GRUPOS]

    def proveedores_por_grupo(self, grupo, ciudad=None, limite=3):
        return self.PROVEEDORES.get(grupo, [])[:limite]


def _repo(monkeypatch):
    """Repo con las consultas SQL sustituidas por datos en memoria."""
    repo = _RepoFalso()
    import src.infrastructure.database.repositories.proveedor_repository as mod

    def fake_execute(sql, params=None, **kwargs):
        if "insumo_referencia_idu" in sql:
            return repo._consultar_bpr((params[0] or "").strip("%").lower())
        if "proveedor_grupo" in sql:
            return repo._consultar_grupos()
        return []

    monkeypatch.setattr(mod, "execute_query", fake_execute)
    return repo


def test_raiz_normaliza_plural_y_genero():
    """'PINTURA' debe casar con el grupo 'PINTURAS', y 'anticorrosiva' con 'ANTICORROSIVO'."""
    assert _raiz("pinturas") == _raiz("pintura")
    assert _raiz("anticorrosiva") == _raiz("anticorrosivo")
    assert _tokens("Pintura anticorrosiva") & _tokens("PINTURAS")


def test_empareja_equipo_con_su_grupo(monkeypatch):
    """El puente por el BPR resuelve lo que el nombre del grupo no dice:
    'MOTONIVELADORA' no comparte ninguna palabra con 'EQUIPO PESADO'."""
    repo = _repo(monkeypatch)
    match = repo.buscar_grupo_de_insumo("MOTONIVELADORA POTENCIA 215 HP")
    assert match is not None
    assert match["grupo"] == "EQUIPO PESADO"
    assert match["precio"] == 327250


def test_prefiere_el_grupo_antes_que_una_mencion_suelta(monkeypatch):
    """'Pintura anticorrosiva' es del grupo PINTURAS, no del acero estructural que
    solo la menciona dentro de su descripción."""
    repo = _repo(monkeypatch)
    match = repo.buscar_grupo_de_insumo("Pintura anticorrosiva")
    assert match is not None
    assert match["grupo"] == "PINTURAS"


def test_no_sugiere_nada_para_un_insumo_desconocido(monkeypatch):
    repo = _repo(monkeypatch)
    assert repo.sugerir_para_insumo("Artefacto inexistente zzz") is None


def test_insumo_sin_precio_recibe_proveedores_sugeridos(monkeypatch):
    """Un 'pendiente de cotización' debe decir a quién pedírsela."""
    repo = _repo(monkeypatch)

    class SinPrecio:
        def buscar_referencia_insumo(self, *a, **kw):
            return None

        def buscar_material(self, *a, **kw):
            return []

        def buscar(self, *a, **kw):
            return []

    # El BPR de este insumo no tiene precio, así que cae hasta el final de la cascada.
    monkeypatch.setattr(repo, "buscar_grupo_de_insumo",
                        lambda desc: {"grupo": "BORDILLOS Y LOSETAS", "codigo_idu": "6116",
                                      "insumo_idu": "BORDILLO", "unidad": "UN",
                                      "precio": None, "similitud": 1.0})

    propuesta = {"insumos": [{"tipo_insumo": "Materiales", "descripcion": "Bordillo prefabricado A80",
                              "unidad": None, "precio": None}]}
    res = _aplicar_jerarquia_precios(
        propuesta=propuesta, solicitud={"ciudad": "Bogotá"},
        cype_source=SinPrecio(), referencia_externa_repo=SinPrecio(),
        materiales_source=SinPrecio(), proveedor_repo_=repo,
    )
    ins = res["insumos"][0]
    assert ins["precio"] is None
    assert ins["grupo_proveedores"] == "BORDILLOS Y LOSETAS"
    assert ins["proveedores_sugeridos"][0]["nombre"] == "INVERSIONES TJ"
    assert "INVERSIONES TJ" in ins["fuente"]


def test_precio_oficial_idu_entra_en_la_cascada(monkeypatch):
    """Con precio en el BPR se usa como fuente, citando el código del insumo."""
    repo = _repo(monkeypatch)

    class SinPrecio:
        def buscar_referencia_insumo(self, *a, **kw):
            return None

        def buscar_material(self, *a, **kw):
            return []

        def buscar(self, *a, **kw):
            return []

    propuesta = {"insumos": [{"tipo_insumo": "Equipos", "descripcion": "MOTONIVELADORA",
                              "unidad": None, "precio": None}]}
    res = _aplicar_jerarquia_precios(
        propuesta=propuesta, solicitud={"ciudad": "Bogotá"},
        cype_source=SinPrecio(), referencia_externa_repo=SinPrecio(),
        materiales_source=SinPrecio(), proveedor_repo_=repo,
    )
    ins = res["insumos"][0]
    assert ins["precio"] == 327250
    assert ins["unidad"] == "HR"
    assert "Banco de Precios IDU" in ins["fuente"]
    assert "6013" in ins["fuente"]
