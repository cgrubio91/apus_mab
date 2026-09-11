"""
Infrastructure: Análisis APU — emparejamiento y búsqueda en banco (MySQL).

Helpers puros de tokens (normalización, Jaccard, compuestos) y funciones de
búsqueda sobre la tabla `apus` que solo usan execute_query/log, sin estado
de instancia. La clase AnalisisMySQLRepository delega en ellas.
"""

import logging
import re
import unicodedata
from typing import Optional

from src.infrastructure.database.connection import execute_query, get_db_connection

log = logging.getLogger("mapus.infrastructure.analisis_matching")

# Palabras vacías que no aportan al emparejamiento por descripción.
_STOPWORDS = {
    "de", "la", "el", "los", "las", "para", "con", "por", "del", "una", "uno",
    "y", "o", "en", "a", "al", "un", "e", "que", "su", "sus", "the",
}

# Tokens cortos (≤3) que SÍ son distintivos en construcción y no deben perderse:
# unidades, siglas de material y grados técnicos.
_TOKENS_TECNICOS = {
    "pvc", "hg", "psi", "acp", "api", "cpc", "hz", "kw", "hp", "rpm", "kva",
    "ml", "kg", "und", "gr", "cm", "mm", "km", "lt", "gl", "pa", "pu", "ac",
}


def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes (NFD + descarta marcas), para comparar 'hormigón'
    con 'hormigon'. La ñ se colapsa a n, lo cual ayuda al emparejamiento."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _token_util(t: str) -> bool:
    """Conserva tokens largos, siglas técnicas y cualquier token con dígitos
    (diámetros, resistencias: '3000', '6', '40hp', 'm3')."""
    if t in _STOPWORDS:
        return False
    if len(t) > 3:
        return True
    if t in _TOKENS_TECNICOS:
        return True
    return any(ch.isdigit() for ch in t)


def _tokenizar(texto: str) -> set:
    """Conjunto de palabras significativas, sin tildes y sin stopwords."""
    if not texto:
        return set()
    tokens = re.findall(r"[a-z0-9]+", _normalizar(texto))
    return {t for t in tokens if _token_util(t)}


def _similitud_tokens(a: set, b: set) -> float:
    """Índice de Jaccard entre dos conjuntos de tokens (0..1)."""
    if not a or not b:
        return 0.0
    interseccion = len(a & b)
    if interseccion == 0:
        return 0.0
    return interseccion / len(a | b)


_PREFIJOS_COMPUESTOS = {"mini", "retro", "micro", "macro", "multi", "super", "semi", "auto", "hidro"}


def _expandir_compuestos(tokens: set) -> set:
    """Expande tokens que pueden ser compuestos o separados.
    'minicargador' → se agrega 'cargador' solo si el token original
    también existe en el otro conjunto (manejado en matching cruzado).
    """
    resultado = set(tokens)
    for t in tokens:
        for p in _PREFIJOS_COMPUESTOS:
            if t.startswith(p) and len(t) > len(p) + 2:
                resultado.add(p)
                resultado.add(t[len(p):])
        if " " in t:
            partes = t.split(None, 1)
            if len(partes[0]) <= 5:
                resultado.add(partes[0] + partes[1])
    return resultado


def _coincidencia_compuesta(token: str, texto: str) -> bool:
    """Verifica si un token aparece como:
    1) palabra completa ('cargador' en 'Cargador: potencia'), o
    2) al final de otra palabra ('cargador' en 'MINICARGADOR 40HP'), o
    3) todas sus partes prefijo+base separadas ('minicargador' en 'mini cargador').
    """
    texto = _normalizar(texto)
    if _coincidencia_palabra_completa(token, texto):
        return True
    if re.search(rf'{re.escape(token)}\b', texto, re.IGNORECASE):
        return True
    for p in _PREFIJOS_COMPUESTOS:
        if token.startswith(p) and len(token) > len(p) + 2:
            stem = token[len(p):]
            if _coincidencia_palabra_completa(p, texto) and _coincidencia_palabra_completa(stem, texto):
                return True
    return False


def _coincidencia_palabra_completa(token: str, texto: str) -> bool:
    """True si token aparece como palabra completa en texto. Ambos lados se
    normalizan (sin tildes) para que 'hormigon' encuentre 'hormigón'."""
    if not token or len(token) < 3:
        return False
    token = _normalizar(token)
    pattern = r'(?<![a-z0-9])' + re.escape(token) + r'(?![a-z0-9])'
    return bool(re.search(pattern, _normalizar(texto)))


def buscar_insumos_candidatos(descripcion: str, max_desc: int = 15) -> list:
    """Descripciones DISTINTAS del banco parecidas al insumo, con flags de
    completitud (si existe alguna fila con unidad / con valor). Trabaja sobre
    descripciones distintas para que los duplicados y outliers no tapen la buena.
    Devuelve [{descripcion, tiene_unidad, tiene_valor, similitud}] ordenado."""
    if not descripcion:
        return []
    objetivo = _tokenizar(descripcion)
    if not objetivo:
        return []
    palabras = sorted(objetivo, key=len, reverse=True)[:6]
    principal = palabras[0]

    _sql = """SELECT insumo_descripcion,
                     MAX(CASE WHEN insumo_unidad IS NOT NULL AND TRIM(insumo_unidad) <> '' THEN 1 ELSE 0 END) AS tiene_unidad,
                     MAX(CASE WHEN precio_unitario_apu > 0 THEN 1 ELSE 0 END) AS tiene_valor,
                     COUNT(*) AS n
              FROM apus
              WHERE {cond}
              GROUP BY insumo_descripcion
              LIMIT 500"""
    with get_db_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(_sql.format(cond="insumo_descripcion LIKE %s"), [f"%{principal}%"])
            descs = cursor.fetchall()
            if not descs and len(palabras) > 1:
                cond = " OR ".join(["insumo_descripcion LIKE %s" for _ in palabras])
                cursor.execute(_sql.format(cond=cond), [f"%{p}%" for p in palabras])
                descs = cursor.fetchall()
    if not descs:
        return []
    for d in descs:
        d["similitud"] = round(_similitud_tokens(objetivo, _tokenizar(d.get("insumo_descripcion", ""))), 3)
    descs = [d for d in descs if d["similitud"] > 0]
    if not descs:
        return []
    # Similitud primero; entre parecidos, las que tienen unidad+valor arriba.
    descs.sort(
        key=lambda d: (d["similitud"], (d.get("tiene_valor") or 0) + (d.get("tiene_unidad") or 0), d.get("n", 0)),
        reverse=True,
    )
    # Umbral suave para quitar ruido lejano, pero conservar variantes (la IA
    # decide luego entre "MINICARGADOR 40HP" y "Cargador: potencia 125 hp").
    top_sim = descs[0]["similitud"]
    umbral = max(0.15, top_sim * 0.25)
    cercanas = [d for d in descs if d["similitud"] >= umbral]
    return (cercanas or descs)[:max_desc]


def referencias_de_descripciones(descripciones: list, max_total: int = 12, por_desc: int = 4) -> list:
    """Filas reales de referencia para las descripciones dadas. Trae unas pocas
    filas POR CADA descripción (prefiriendo con unidad+valor), para que ninguna
    quede tapada por el precio de otra. Devuelve deduplicadas."""
    descripciones = [d for d in (descripciones or []) if d]
    if not descripciones:
        return []
    sql = """SELECT insumo_descripcion, insumo_unidad, tipo_insumo, rendimiento_insumo,
                    precio_unitario_apu, precio_parcial_apu, nombre_proyecto, entidad,
                    ciudad, contratista, fecha_aprobacion_apu AS fecha
             FROM apus
             WHERE insumo_descripcion = %s
             ORDER BY (insumo_unidad IS NOT NULL AND TRIM(insumo_unidad) <> '') DESC,
                      (precio_unitario_apu > 0) DESC,
                      precio_unitario_apu DESC
             LIMIT %s"""
    filas = []
    with get_db_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:
            for desc in descripciones:
                cursor.execute(sql, (desc, por_desc))
                filas.extend(cursor.fetchall())

    vistos = set()
    top = []
    for f in filas:
        clave = (f.get("insumo_descripcion"), f.get("nombre_proyecto"),
                 f.get("insumo_unidad"), f.get("precio_unitario_apu"))
        if clave in vistos:
            continue
        vistos.add(clave)
        f["similitud"] = None
        top.append(f)
    return top[: max_total * 3]


def buscar_insumos_similares(descripcion: str, max_ref: int = 12) -> list:
    """Descripciones distintas parecidas → filas reales de referencia, ordenadas
    por SIMILITUD, luego por lo más COMPLETO (unidad+valor+rend.), luego precio."""
    candidatos = buscar_insumos_candidatos(descripcion, max_desc=max_ref)
    descripciones = [c["insumo_descripcion"] for c in candidatos]
    refs = referencias_de_descripciones(descripciones, max_total=max_ref * 2)
    # Similitud calculada directo por fila (robusto ante may/min y espacios).
    objetivo = _tokenizar(descripcion)
    for r in refs:
        r["similitud"] = round(_similitud_tokens(objetivo, _tokenizar(r.get("insumo_descripcion", ""))), 3)

    def _compl(r: dict) -> int:
        n = 0
        if r.get("precio_unitario_apu") and float(r["precio_unitario_apu"]) > 0:
            n += 1
        if r.get("insumo_unidad") and str(r["insumo_unidad"]).strip():
            n += 1
        if r.get("rendimiento_insumo") is not None:
            n += 1
        return n

    refs.sort(key=lambda r: (round(r["similitud"], 3), _compl(r), float(r.get("precio_unitario_apu") or 0)), reverse=True)
    return refs[:max_ref]


def buscar_en_banco(descripcion: str) -> list:
    if not descripcion:
        return []
    palabras = [p for p in descripcion.split() if len(p) > 3][:5]
    if not palabras:
        return []
    condiciones = " OR ".join([f"items_descripcion LIKE %s" for _ in palabras])
    params = [f"%{p}%" for p in palabras]
    params.extend([descripcion[:10]])
    with get_db_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(
                f"""SELECT item, items_descripcion,
                           item_unidad, precio_unitario, precio_unitario_sin_aiu,
                           rendimiento_insumo, tipo_insumo, codigo_insumo,
                           insumo_descripcion, insumo_unidad
                    FROM apus
                    WHERE ({condiciones} OR items_descripcion LIKE %s)
                      AND precio_unitario IS NOT NULL
                    GROUP BY items_descripcion, item, item_unidad, precio_unitario,
                             precio_unitario_sin_aiu, rendimiento_insumo, tipo_insumo,
                             codigo_insumo, insumo_descripcion, insumo_unidad
                    ORDER BY items_descripcion, precio_unitario ASC
                    LIMIT 5""",
                params,
            )
            return cursor.fetchall()


def buscar_apus_similares(descripcion: str, insumos_desc: Optional[list] = None,
                          max_candidatos: int = 5, max_insumos: int = 40) -> list:
    """Devuelve los APUs del banco más parecidos al ítem cotizado.

    Criterio de emparejamiento (en orden de prioridad):
      1. Descripción del ítem (que hable del mismo trabajo).
      2. Estructura del APU: mayor cantidad de insumos similares.
    El precio/rendimiento/unidad se comparan después, ya sobre el equivalente elegido.
    """
    # Tokens del ITEM (criterio primario) separados de los tokens de INSUMOS (secundario).
    tokens_item = _tokenizar(descripcion or "")
    if not tokens_item:
        return []
    tokens_item_exp = _expandir_compuestos(tokens_item)

    tokens_insumos: set = set()
    for d in (insumos_desc or []):
        tokens_insumos |= _tokenizar(d or "")

    # El pool de candidatos se arma con la DESCRIPCIÓN DEL ÍTEM (no con los insumos),
    # para no traer APUs de otro trabajo que solo comparten un equipo (ej. minicargador).
    expansion_larga = {t for t in (tokens_item_exp - tokens_item) if len(t) >= 5}
    candidatos_palabras = [p for p in sorted(tokens_item | expansion_larga, key=len, reverse=True) if len(p) >= 4]
    palabras = candidatos_palabras[:4] if candidatos_palabras else sorted(tokens_item, key=len, reverse=True)[:3]
    # Tokens distintivos del ítem para exigir que el candidato hable del mismo trabajo.
    tokens_distintivos = [t for t in tokens_item if len(t) >= 5] or list(tokens_item)

    like_item = " OR ".join(["items_descripcion LIKE %s" for _ in palabras])
    params = [f"%{p}%" for p in palabras]

    with get_db_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(
                f"""SELECT numero_contrato, link_documento, item, items_descripcion, item_unidad,
                           nombre_proyecto, entidad, ciudad, contratista,
                           MAX(precio_unitario) AS precio_unitario,
                           MAX(precio_unitario_sin_aiu) AS precio_unitario_sin_aiu,
                           MAX(fecha_aprobacion_apu) AS fecha,
                           COUNT(*) AS num_insumos,
                           MAX(CASE WHEN precio_unitario_apu > 0 THEN 1 ELSE 0 END) AS tiene_valor,
                           MAX(CASE WHEN rendimiento_insumo IS NOT NULL AND rendimiento_insumo > 0 THEN 1 ELSE 0 END) AS tiene_rendimiento,
                           GROUP_CONCAT(DISTINCT insumo_descripcion SEPARATOR ' | ') AS insumos_texto
                    FROM apus
                    WHERE ({like_item})
                    GROUP BY numero_contrato, link_documento, item, items_descripcion,
                             item_unidad, nombre_proyecto, entidad, ciudad, contratista
                    ORDER BY num_insumos DESC
                    LIMIT 300""",
                params,
            )
            candidatos = cursor.fetchall()
            if not candidatos:
                return []

            # Tokens de cada insumo cotizado, para medir cuántos tienen homólogo en el candidato.
            insumos_objetivo = [_tokenizar(d or "") for d in (insumos_desc or [])]
            insumos_objetivo = [t for t in insumos_objetivo if t]

            for c in candidatos:
                # (1) PRIMARIO: parecido de la DESCRIPCIÓN DEL ÍTEM (mismo trabajo).
                desc_cand = c.get("items_descripcion") or ""
                tokens_desc_cand = _expandir_compuestos(_tokenizar(desc_cand))
                c["_sim_item"] = _similitud_tokens(tokens_item_exp, tokens_desc_cand)
                # El candidato debe hablar del mismo trabajo: algún token distintivo del ítem
                # aparece en SU DESCRIPCIÓN (no en sus insumos).
                c["_habla_del_item"] = any(
                    _coincidencia_compuesta(t, desc_cand) for t in tokens_distintivos
                )
                # (2) SECUNDARIO: estructura del APU — nº de insumos cotizados con homólogo.
                tokens_ins_cand = _expandir_compuestos(_tokenizar(c.get("insumos_texto") or ""))
                coincidentes = 0
                for tset in insumos_objetivo:
                    principal = max(tset, key=len)
                    if principal in tokens_ins_cand or _similitud_tokens(tset, tokens_ins_cand) >= 0.15:
                        coincidentes += 1
                c["_insumos_match"] = coincidentes

            # Solo candidatos cuya DESCRIPCIÓN DE ÍTEM se parezca al ítem cotizado.
            candidatos = [
                c for c in candidatos
                if c["_sim_item"] > 0 and c["_habla_del_item"]
            ]

            def _completitud_apu(c: dict) -> int:
                n = int(c.get("tiene_valor", 0) or 0)
                if c.get("item_unidad") and str(c["item_unidad"]).strip():
                    n += 1
                if int(c.get("tiene_rendimiento", 0) or 0):
                    n += 1
                return n

            # Orden: 1º descripción del ítem, 2º estructura (insumos similares), luego completitud.
            candidatos.sort(
                key=lambda c: (round(c["_sim_item"], 3), c["_insumos_match"],
                               _completitud_apu(c), c.get("num_insumos", 0)),
                reverse=True,
            )
            top = candidatos[:max_candidatos]

            for c in top:
                cursor.execute(
                    """SELECT tipo_insumo, codigo_insumo, insumo_descripcion, insumo_unidad,
                              rendimiento_insumo, precio_unitario_apu, precio_parcial_apu
                       FROM apus
                       WHERE numero_contrato <=> %s AND link_documento <=> %s
                         AND item <=> %s AND items_descripcion <=> %s
                         AND nombre_proyecto <=> %s
                       ORDER BY tipo_insumo, insumo_descripcion
                       LIMIT %s""",
                    (c.get("numero_contrato"), c.get("link_documento"), c.get("item"),
                     c.get("items_descripcion"), c.get("nombre_proyecto"), max_insumos),
                )
                c["insumos"] = cursor.fetchall()
                c["similitud"] = round(c.pop("_sim_item", 0.0), 3)
                c["insumos_coincidentes"] = c.pop("_insumos_match", 0)
                c.pop("insumos_texto", None)
                c.pop("tiene_valor", None)
                c.pop("tiene_rendimiento", None)
                c.pop("_habla_del_item", None)
            return top
