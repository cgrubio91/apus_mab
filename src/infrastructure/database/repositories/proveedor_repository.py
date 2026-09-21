"""
Infrastructure: Repositorio del directorio de proveedores del IDU (MySQL)

Responde "¿a quién le pido cotización de este insumo?".

El puente entre un insumo del APU y sus proveedores es el `grupo` del IDU, que
comparten `insumo_referencia_idu` (Banco de Precios de Referencia) y
`proveedor_grupo` (directorio de cotizaciones):

    insumo del APU → insumo del BPR → grupo → proveedores

Buscar primero contra los ~2.700 nombres del BPR (descripciones reales de
insumo) es bastante más preciso que comparar contra los 84 nombres de grupo,
que son categorías: "MOTONIVELADORA 215 HP" no comparte ninguna palabra con
"EQUIPO PESADO", pero sí con el insumo homónimo del BPR.
"""

import logging
import re
import unicodedata
from typing import Optional

from src.infrastructure.database.connection import execute_query

log = logging.getLogger("mapus.infrastructure.proveedor_repo")

_PALABRAS_VACIAS = {
    "para", "tipo", "con", "sin", "por", "los", "las", "del", "una", "uno",
    "segun", "otro", "otros", "que", "suministro", "instalacion", "incluye",
    "insumo", "insumos", "elemento", "elementos",
}
# Cobertura mínima del nombre del insumo buscado para aceptar una coincidencia.
_UMBRAL_COINCIDENCIA = 0.5
# Para la ruta por nombre de grupo basta media coincidencia ("MALLAS Y ACEROS
# PARA REFUERZO" tiene 4 palabras y un insumo rara vez las nombra todas).
_UMBRAL_GRUPO = 0.34
_MAX_ANCLAS = 3


def _principal(texto: Optional[str]) -> str:
    """Primera palabra significativa: suele nombrar el material ('Pintura …')."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    for w in re.findall(r"[a-z0-9]+", t):
        if len(w) > 3 and w not in _PALABRAS_VACIAS:
            return _raiz(w)
    return ""


def _raiz(palabra: str) -> str:
    """Stem mínimo en español: plural y género.

    Sin esto 'PINTURA' no casa con el grupo 'PINTURAS', ni 'anticorrosiva' con
    el insumo 'ANTICORROSIVO' del BPR.
    """
    for sufijo in ("es", "s"):
        if len(palabra) > 4 and palabra.endswith(sufijo):
            palabra = palabra[: -len(sufijo)]
            break
    if len(palabra) > 4 and palabra[-1] in "oa":
        palabra = palabra[:-1]
    return palabra


def _tokens(texto: Optional[str]) -> set:
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return {
        _raiz(w) for w in re.findall(r"[a-z0-9]+", t)
        if len(w) > 3 and w not in _PALABRAS_VACIAS
    }


class ProveedorRepository:

    def buscar_grupo_de_insumo(self, descripcion: str) -> Optional[dict]:
        """Grupo del IDU que mejor corresponde a la descripción de un insumo.

        Devuelve también el insumo del BPR que hizo la coincidencia (con su
        precio oficial), porque sirve de soporte en la propuesta.
        """
        objetivo = _tokens(descripcion)
        if not objetivo:
            return None

        # Prefiltro en SQL por unas pocas anclas, para no traer las 2.740 filas.
        # Se prueban varias porque con una sola ("Neopreno reforzado" → 'reforzado')
        # el prefiltro puede no devolver ningún candidato correcto.
        principal = _principal(descripcion)
        anclas = [a for a in ([principal] if principal else []) +
                  sorted(objetivo, key=len, reverse=True) if a][:_MAX_ANCLAS]

        candidatos, vistos = [], set()
        for ancla in anclas:
            for f in execute_query(
                """SELECT codigo, grupo, nombre, unidad, precio
                   FROM insumo_referencia_idu
                   WHERE grupo IS NOT NULL AND nombre LIKE %s
                   LIMIT 200""",
                (f"%{ancla}%",),
            ) or []:
                if f["codigo"] not in vistos:
                    vistos.add(f["codigo"])
                    candidatos.append(f)

        mejor, mejor_score = None, 0.0
        for f in candidatos:
            tokens_f = _tokens(f.get("nombre"))
            comunes = objetivo & tokens_f
            # Sin la palabra principal no es el mismo insumo: evita que
            # "Insumo inventado xyz" se lleve cualquier fila por una palabra suelta.
            if not comunes or (principal and principal not in comunes):
                continue
            score = len(comunes) / len(objetivo)
            # Que el nombre del BPR EMPIECE por lo mismo desempata: sin esto
            # "pintura anticorrosiva" caía en una tubería "con pintura anticorrosiva".
            primeros = _tokens(" ".join((f.get("nombre") or "").split()[:2]))
            if principal and principal in primeros:
                score += 0.5
            if score > mejor_score:
                mejor, mejor_score = f, score

        via_bpr = None
        if mejor and mejor_score >= _UMBRAL_COINCIDENCIA:
            via_bpr = {
                "grupo": mejor["grupo"],
                "codigo_idu": mejor["codigo"],
                "insumo_idu": mejor["nombre"],
                "unidad": mejor.get("unidad"),
                "precio": mejor.get("precio"),
                "similitud": round(mejor_score, 3),
            }

        # Segunda ruta: comparar contra el nombre del grupo. Cubre lo que el BPR
        # resuelve mal, p.ej. "pintura anticorrosiva" casa de lleno con el grupo
        # "PINTURAS", mientras que en el BPR la frase aparece dentro de la
        # descripción de un acero estructural y se lo llevaba a ESTRUCTURAS EN ACERO.
        via_grupo = self._grupo_por_nombre(objetivo, principal)

        if via_grupo and (not via_bpr or via_grupo["similitud"] >= via_bpr["similitud"]):
            return via_grupo
        return via_bpr

    def _grupo_por_nombre(self, objetivo: set, principal: str) -> Optional[dict]:
        """Coincidencia directa contra los nombres de grupo del directorio."""
        if not principal:
            return None
        mejor, mejor_score = None, 0.0
        for fila in execute_query("SELECT DISTINCT grupo FROM proveedor_grupo") or []:
            grupo = fila["grupo"]
            tokens_grupo = _tokens(grupo)
            if not tokens_grupo or principal not in tokens_grupo:
                continue
            # Cobertura del NOMBRE DEL GRUPO: "PINTURAS" (1 palabra) cubierta por
            # "pintura" vale 1.0; un grupo de 5 palabras con una coincidencia, no.
            score = len(objetivo & tokens_grupo) / len(tokens_grupo)
            if score > mejor_score:
                mejor, mejor_score = grupo, score
        if not mejor or mejor_score < _UMBRAL_GRUPO:
            return None
        return {
            "grupo": mejor,
            "codigo_idu": None,
            "insumo_idu": None,
            "unidad": None,
            "precio": None,
            "similitud": round(mejor_score, 3),
        }

    def proveedores_por_grupo(self, grupo: str, ciudad: Optional[str] = None,
                              limite: int = 3) -> list[dict]:
        """Proveedores de un grupo, priorizando los de la ciudad de la obra."""
        if not grupo:
            return []
        # `cotizo` marca a quien ya respondió cotizaciones antes: mejor candidato.
        return execute_query(
            """SELECT p.nombre, p.municipio, p.departamento, p.telefono,
                      p.web_correo, p.contacto
               FROM proveedor p
               JOIN proveedor_grupo pg ON pg.proveedor_id = p.id
               WHERE pg.grupo = %s
               ORDER BY (TRIM(LOWER(p.municipio)) = TRIM(LOWER(%s))) DESC,
                        p.cotizo DESC, p.nombre
               LIMIT %s""",
            (grupo, (ciudad or "").strip(), int(limite)),
        ) or []

    def sugerir_para_insumo(self, descripcion: str, ciudad: Optional[str] = None,
                            limite: int = 3) -> Optional[dict]:
        """Grupo + proveedores sugeridos para un insumo sin precio."""
        match = self.buscar_grupo_de_insumo(descripcion)
        if not match:
            return None
        proveedores = self.proveedores_por_grupo(match["grupo"], ciudad=ciudad, limite=limite)
        if not proveedores:
            return None
        return {**match, "proveedores": proveedores}


proveedor_repo = ProveedorRepository()
