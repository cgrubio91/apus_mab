"""
Infrastructure: Análisis APU Repository Implementation (MySQL)
"""

import json
import logging
import re
import unicodedata
from datetime import date, timedelta
from typing import Optional

import mysql.connector

from src.infrastructure.database.connection import get_db_connection, execute_query

log = logging.getLogger("mapus.infrastructure.analisis_repo")

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


class AnalisisMySQLRepository:

    def crear_solicitud(self, grupos_insumos: list[dict], proyecto_id: Optional[int] = None,
                        tipo_comparacion: Optional[str] = None) -> int:
        all_insumos = []
        for grupo in grupos_insumos:
            all_insumos.extend(grupo.get("insumos", []))

        contratista = self._extraer_campo_comun(all_insumos, "contratista") or "Sin contratista"
        nombre_proyecto = self._extraer_campo_comun(all_insumos, "nombre_proyecto") or "Sin proyecto"
        link_documento = ", ".join(
            g.get("nombre_archivo", f"Archivo {i+1}")
            for i, g in enumerate(grupos_insumos)
        )

        try:
            with get_db_connection() as conn:
                with conn.cursor(dictionary=True) as cursor:
                    cursor.execute(
                        """INSERT INTO solicitudes_apu (link_documento, contratista, nombre_proyecto, estado, proyecto_id, tipo_comparacion)
                           VALUES (%s, %s, %s, 'pendiente_analisis', %s, %s)""",
                        (link_documento, contratista, nombre_proyecto, proyecto_id, tipo_comparacion),
                    )
                    solicitud_id = cursor.lastrowid

                    for grupo in grupos_insumos:
                        grupo_idx = grupo.get("grupo_cotizacion", 1)
                        nombre_archivo = grupo.get("nombre_archivo", "")
                        for ins in grupo.get("insumos", []):
                            cursor.execute(
                                """INSERT INTO solicitud_insumos
                                   (solicitud_id, grupo_cotizacion, nombre_archivo,
                                    item, items_descripcion, item_unidad, precio_unitario,
                                    codigo_insumo, insumo_descripcion, insumo_unidad,
                                    rendimiento_insumo, precio_unitario_apu, precio_parcial_apu,
                                    tipo_insumo)
                                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                                (solicitud_id, grupo_idx, nombre_archivo,
                                 ins.get("item"), ins.get("items_descripcion"),
                                 ins.get("item_unidad"), ins.get("precio_unitario"),
                                 ins.get("codigo_insumo"), ins.get("insumo_descripcion"),
                                 ins.get("insumo_unidad"), ins.get("rendimiento_insumo"),
                                 ins.get("precio_unitario_apu"), ins.get("precio_parcial_apu"),
                                 ins.get("tipo_insumo")),
                            )

                    conn.commit()
                    log.info("Solicitud %d creada: %s - %s", solicitud_id, contratista, nombre_proyecto)
                    return solicitud_id
        except Exception:
            log.exception("Error creando solicitud")
            raise

    def crear_borrador(self, descripcion_actividad: str, unidad_actividad: Optional[str],
                       codigo_item: Optional[str], ciudad: Optional[str],
                       proyecto_id: Optional[int]) -> int:
        """Crea una solicitud en estado 'borrador' originada en el Constructor de APU."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO solicitudes_apu
                           (estado, origen, tipo_comparacion, contratista, nombre_proyecto,
                            descripcion_actividad, unidad_actividad, codigo_item, ciudad, proyecto_id)
                           VALUES ('borrador', 'constructor', 'apu', 'Por asignar', 'Constructor MAPUS',
                                   %s, %s, %s, %s, %s)""",
                        (descripcion_actividad, unidad_actividad, codigo_item, ciudad, proyecto_id),
                    )
                    solicitud_id = cursor.lastrowid
                    conn.commit()
                    log.info("Borrador de APU %d creado (actividad: %s)", solicitud_id, descripcion_actividad[:80])
                    return solicitud_id
        except Exception:
            log.exception("Error creando borrador de APU")
            raise

    def reemplazar_insumos_estructura(self, solicitud_id: int, filas: list[dict]) -> None:
        """Reemplaza TODOS los insumos de la solicitud por la estructura indicada
        (Constructor de APU). Cada fila trae tipo/desc/und/rendimiento y los datos
        del banco (precio_banco, rendimiento_banco, fuente_precio)."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM solicitud_insumos WHERE solicitud_id = %s", (solicitud_id,))
                    for f in filas:
                        cursor.execute(
                            """INSERT INTO solicitud_insumos
                               (solicitud_id, grupo_cotizacion, nombre_archivo,
                                item, items_descripcion, item_unidad,
                                codigo_insumo, insumo_descripcion, insumo_unidad,
                                rendimiento_insumo, precio_unitario_apu, precio_parcial_apu, tipo_insumo,
                                precio_banco, rendimiento_banco, fuente_precio)
                               VALUES (%s, 1, 'Estructura Constructor', %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s, %s, %s, %s)""",
                            (solicitud_id, f.get("item"), f.get("items_descripcion"), f.get("item_unidad"),
                             f.get("codigo_insumo"), f.get("insumo_descripcion"), f.get("insumo_unidad"),
                             f.get("rendimiento_insumo"), f.get("tipo_insumo"),
                             f.get("precio_banco"), f.get("rendimiento_banco"), f.get("fuente_precio")),
                        )
                    conn.commit()
        except Exception:
            log.exception("Error reemplazando estructura de insumos de solicitud %d", solicitud_id)
            raise

    def insertar_insumo_estructura(self, solicitud_id: int, fila: dict) -> int:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO solicitud_insumos
                           (solicitud_id, grupo_cotizacion, nombre_archivo,
                            item, items_descripcion, item_unidad,
                            codigo_insumo, insumo_descripcion, insumo_unidad,
                            rendimiento_insumo, precio_unitario_apu, precio_parcial_apu, tipo_insumo,
                            precio_banco, rendimiento_banco, fuente_precio)
                           VALUES (%s, 1, 'Estructura Constructor', %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s, %s, %s, %s)""",
                        (solicitud_id, fila.get("item"), fila.get("items_descripcion"), fila.get("item_unidad"),
                         fila.get("codigo_insumo"), fila.get("insumo_descripcion"), fila.get("insumo_unidad"),
                         fila.get("rendimiento_insumo"), fila.get("tipo_insumo"),
                         fila.get("precio_banco"), fila.get("rendimiento_banco"), fila.get("fuente_precio")),
                    )
                    insumo_id = cursor.lastrowid
                    conn.commit()
                    return insumo_id
        except Exception:
            log.exception("Error insertando insumo en borrador %d", solicitud_id)
            raise

    def actualizar_precio_insumo(self, solicitud_id: int, insumo_id: int,
                                 precio_unitario: Optional[float],
                                 precio_parcial: Optional[float] = None) -> bool:
        """Fija el precio del CONTRATISTA para un insumo del borrador (precio_unitario_apu).
        Los datos del banco (precio_banco/fuente) se conservan intactos para comparar."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """UPDATE solicitud_insumos SET precio_unitario_apu = %s,
                               precio_parcial_apu = COALESCE(%s, precio_parcial_apu)
                           WHERE id = %s AND solicitud_id = %s""",
                        (precio_unitario, precio_parcial, insumo_id, solicitud_id),
                    )
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception:
            log.exception("Error actualizando precio de insumo %d (solicitud %d)", insumo_id, solicitud_id)
            raise

    def eliminar_insumo_estructura(self, solicitud_id: int, insumo_id: int) -> bool:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM solicitud_insumos WHERE id = %s AND solicitud_id = %s",
                        (insumo_id, solicitud_id),
                    )
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception:
            log.exception("Error eliminando insumo %d de solicitud %d", insumo_id, solicitud_id)
            raise

    def rellenar_datos_item(self, solicitud_id: int, codigo_item: str, descripcion: str, unidad: str) -> None:
        """Estampa el código/descripción/unidad del ítem en todas las filas del borrador
        (necesario para que el análisis y la migración al presupuesto funcionen)."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """UPDATE solicitud_insumos
                           SET item = %s, items_descripcion = %s, item_unidad = %s
                           WHERE solicitud_id = %s""",
                        (codigo_item, descripcion, unidad, solicitud_id),
                    )
                    cursor.execute(
                        "UPDATE solicitudes_apu SET codigo_item = %s WHERE id = %s",
                        (codigo_item, solicitud_id),
                    )
                    conn.commit()
        except Exception:
            log.exception("Error rellenando datos de ítem en solicitud %d", solicitud_id)
            raise

    def get_solicitudes(self, estado: Optional[str] = None) -> list:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                base_query = """
                    SELECT sa.*,
                           (SELECT items_descripcion FROM solicitud_insumos
                            WHERE solicitud_id = sa.id ORDER BY grupo_cotizacion, id LIMIT 1) as primer_item,
                           (SELECT COUNT(*) FROM solicitud_insumos WHERE solicitud_id = sa.id) as total_items
                    FROM solicitudes_apu sa
                """
                if estado:
                    cursor.execute(base_query + " WHERE sa.estado = %s ORDER BY sa.created_at DESC", (estado,))
                else:
                    cursor.execute(base_query + " ORDER BY sa.created_at DESC")
                return cursor.fetchall()

    def get_solicitud(self, solicitud_id: int) -> Optional[dict]:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT * FROM solicitudes_apu WHERE id = %s", (solicitud_id,))
                solicitud = cursor.fetchone()
                if not solicitud:
                    return None

                cursor.execute(
                    "SELECT * FROM solicitud_insumos WHERE solicitud_id = %s ORDER BY grupo_cotizacion, id",
                    (solicitud_id,),
                )
                solicitud["insumos"] = cursor.fetchall()

                cursor.execute(
                    """SELECT DISTINCT grupo_cotizacion, nombre_archivo
                       FROM solicitud_insumos WHERE solicitud_id = %s ORDER BY grupo_cotizacion""",
                    (solicitud_id,),
                )
                solicitud["grupos_archivos"] = cursor.fetchall()

                cursor.execute(
                    "SELECT * FROM historial_aprobaciones WHERE solicitud_id = %s ORDER BY created_at",
                    (solicitud_id,),
                )
                solicitud["historial"] = cursor.fetchall()

                cursor.execute("SELECT * FROM analisis_apu WHERE solicitud_id = %s", (solicitud_id,))
                analisis = cursor.fetchone()
                if analisis:
                    if analisis.get("analisis_json"):
                        try:
                            parsed = json.loads(analisis["analisis_json"])
                            if isinstance(parsed, dict):
                                analisis["items_analizados"] = parsed.get("items", [])
                                analisis["comparacion_grupos"] = parsed.get("comparacion_grupos")
                                analisis["modo"] = parsed.get("modo", "apu")
                                analisis["insumos_comparados"] = parsed.get("insumos_comparados", [])
                            elif isinstance(parsed, list):
                                analisis["items_analizados"] = parsed
                        except (json.JSONDecodeError, TypeError):
                            analisis["items_analizados"] = []
                    solicitud["analisis"] = analisis

                return solicitud

    def guardar_analisis(self, solicitud_id: int, analisis_json: str, resumen: str, recomendacion: str, conn=None):
        owns_conn = conn is None
        if owns_conn:
            conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO analisis_apu (solicitud_id, analisis_json, resumen, recomendacion)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                           analisis_json = VALUES(analisis_json),
                           resumen = VALUES(resumen),
                           recomendacion = VALUES(recomendacion)""",
                    (solicitud_id, analisis_json, resumen, recomendacion),
                )
                if owns_conn:
                    conn.commit()
        finally:
            if owns_conn and conn:
                conn.close()

    def actualizar_estado(self, solicitud_id: int, estado: str, extra_where: str = "", conn=None) -> bool:
        owns_conn = conn is None
        if owns_conn:
            conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE solicitudes_apu SET estado = %s, updated_at = NOW() WHERE id = %s {extra_where}",
                    (estado, solicitud_id),
                )
                if owns_conn:
                    conn.commit()
                return cursor.rowcount > 0
        finally:
            if owns_conn and conn:
                conn.close()

    def insertar_historial(self, solicitud_id: int, accion: str, rol: str, nombre: str, motivo: Optional[str] = None, conn=None):
        owns_conn = conn is None
        if owns_conn:
            conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO historial_aprobaciones
                       (solicitud_id, accion, responsable_rol, responsable_nombre, motivo)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (solicitud_id, accion, rol, nombre, motivo),
                )
                if owns_conn:
                    conn.commit()
        finally:
            if owns_conn and conn:
                conn.close()

    def insertar_aprendizaje(self, analisis_id: int, motivo: str, contexto: str, conn=None):
        owns_conn = conn is None
        if owns_conn:
            conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO aprendizaje_rechazos (analisis_id, motivo_rechazo, contexto)
                       VALUES (%s, %s, %s)""",
                    (analisis_id, motivo, contexto),
                )
                if owns_conn:
                    conn.commit()
        finally:
            if owns_conn and conn:
                conn.close()

    def get_aprendizaje_rechazos(self, limit: int = 20) -> list:
        try:
            rows = execute_query(
                """SELECT ar.*, a.solicitud_id, sa.contratista, sa.nombre_proyecto
                   FROM aprendizaje_rechazos ar
                   LEFT JOIN analisis_apu a ON ar.analisis_id = a.id
                   LEFT JOIN solicitudes_apu sa ON a.solicitud_id = sa.id
                   ORDER BY ar.created_at DESC LIMIT %s""",
                (limit,),
            )
            return rows or []
        except Exception:
            log.exception("Error obteniendo aprendizaje de rechazos")
            return []

    def _extraer_campo_comun(self, insumos: list, campo: str) -> Optional[str]:
        valores = [str(ins.get(campo, "")).strip() for ins in insumos if ins.get(campo)]
        if valores:
            from collections import Counter
            return Counter(valores).most_common(1)[0][0]
        return None

    def _analizar_mejor_grupo(self, insumos: list, items_analizados: list) -> dict:
        grupos = {}
        for ins in insumos:
            g = ins.get("grupo_cotizacion", 1)
            p = float(ins.get("precio_unitario") or 0)
            if g not in grupos:
                grupos[g] = {"total": 0, "count": 0, "archivo": ins.get("nombre_archivo", f"Cotización {g}")}
            grupos[g]["total"] += p
            grupos[g]["count"] += 1

        mejor_grupo = None
        mejor_promedio = float("inf")
        for g, info in grupos.items():
            prom = info["total"] / info["count"] if info["count"] > 0 else 0
            info["promedio"] = prom
            if prom < mejor_promedio:
                mejor_promedio = prom
                mejor_grupo = g

        return {"mejor_grupo": mejor_grupo, "grupos": grupos, "total_grupos": len(grupos)}

    def resolver_proyecto_por_nombre(self, nombre_proyecto: str) -> Optional[int]:
        if not nombre_proyecto or nombre_proyecto in ("Sin proyecto", ""):
            return None
        try:
            with get_db_connection() as conn:
                with conn.cursor(dictionary=True) as cursor:
                    cursor.execute(
                        """SELECT id FROM proyectos
                           WHERE descripcion LIKE %s
                           LIMIT 1""",
                        (f"%{nombre_proyecto}%",),
                    )
                    row = cursor.fetchone()
                    if row:
                        return row["id"]
                    log.info("Proyecto '%s' no encontrado — requiere selección manual", nombre_proyecto)
                    return None
        except Exception:
            log.exception("Error resolviendo proyecto para '%s'", nombre_proyecto)
            return None

    def actualizar_tipo_comparacion(self, solicitud_id: int, tipo: str, conn=None):
        owns_conn = conn is None
        if owns_conn:
            conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE solicitudes_apu SET tipo_comparacion = %s WHERE id = %s",
                    (tipo, solicitud_id),
                )
                if owns_conn:
                    conn.commit()
        finally:
            if owns_conn and conn:
                conn.close()

    def buscar_insumos_candidatos(self, descripcion: str, max_desc: int = 15) -> list:
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

    def referencias_de_descripciones(self, descripciones: list, max_total: int = 12, por_desc: int = 4) -> list:
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

    def buscar_insumos_similares(self, descripcion: str, max_ref: int = 12) -> list:
        """Descripciones distintas parecidas → filas reales de referencia, ordenadas
        por SIMILITUD, luego por lo más COMPLETO (unidad+valor+rend.), luego precio."""
        candidatos = self.buscar_insumos_candidatos(descripcion, max_desc=max_ref)
        descripciones = [c["insumo_descripcion"] for c in candidatos]
        refs = self.referencias_de_descripciones(descripciones, max_total=max_ref * 2)
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

    def existe_proyecto(self, proyecto_id: int) -> bool:
        rows = execute_query("SELECT id FROM proyectos WHERE id = %s", (proyecto_id,))
        return bool(rows)

    def actualizar_proyecto_id(self, solicitud_id: int, proyecto_id: int, conn=None):
        owns_conn = conn is None
        if owns_conn:
            conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE solicitudes_apu SET proyecto_id = %s WHERE id = %s",
                    (proyecto_id, solicitud_id),
                )
                if owns_conn:
                    conn.commit()
        finally:
            if owns_conn and conn:
                conn.close()

    def crear_item_proyecto(self, solicitud_id: int, proyecto_id: int, item_code: str, descripcion: str,
                             unidad: str, valor_unitario: float, conn=None) -> int:
        owns_conn = conn is None
        if owns_conn:
            conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # nivel=1 / parent_id=NULL: el flujo de APU no captura a qué capítulo
                # pertenece la cotización, así que el ítem NP queda sin jerarquía asignada.
                cursor.execute(
                    """INSERT INTO item_proyecto
                       (proyecto, nivel, codigo, nombre, unidad_medida, cantidad_presupuestada,
                        valor_unitario, valor_presupuestado, tipo_item,
                        aprobado_interventoria, apu_solicitud_id, aprobado_costos)
                        VALUES (%s, 1, %s, %s, %s, %s, %s, %s, 'NP', 1, %s, 1)""",
                    (proyecto_id, item_code, descripcion, unidad, 1,
                     valor_unitario, valor_unitario, solicitud_id),
                )
                item_id = cursor.lastrowid
                if owns_conn:
                    conn.commit()
                log.info("Item_proyecto %d creado desde APU solicitud %d: %s", item_id, solicitud_id, item_code)
                return item_id
        except Exception:
            log.exception("Error creando item_proyecto desde APU solicitud %d", solicitud_id)
            if owns_conn:
                conn.rollback()
            raise
        finally:
            if owns_conn and conn:
                conn.close()

    def buscar_en_banco(self, descripcion: str) -> list:
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

    def buscar_apus_similares(self, descripcion: str, insumos_desc: Optional[list] = None,
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

    def eliminar_solicitud(self, solicitud_id: int) -> bool:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM aprendizaje_rechazos WHERE analisis_id IN (SELECT id FROM analisis_apu WHERE solicitud_id = %s)",
                        (solicitud_id,),
                    )
                    cursor.execute("DELETE FROM solicitudes_apu WHERE id = %s", (solicitud_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception:
            log.exception("Error eliminando solicitud %d", solicitud_id)
            raise


analisis_repo = AnalisisMySQLRepository()