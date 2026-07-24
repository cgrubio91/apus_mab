"""
Infrastructure: Análisis APU Repository Implementation (MySQL)
"""

import json
import logging
import re
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


def _tokenizar(texto: str) -> set:
    """Devuelve el conjunto de palabras significativas (>3 letras, sin stopwords)."""
    if not texto:
        return set()
    tokens = re.findall(r"[a-záéíóúñ0-9]+", texto.lower())
    return {t for t in tokens if len(t) > 3 and t not in _STOPWORDS}


def _similitud_tokens(a: set, b: set) -> float:
    """Índice de Jaccard entre dos conjuntos de tokens (0..1)."""
    if not a or not b:
        return 0.0
    interseccion = len(a & b)
    if interseccion == 0:
        return 0.0
    return interseccion / len(a | b)


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

    def buscar_insumos_similares(self, descripcion: str, max_ref: int = 5) -> list:
        """Referencias de precio de un insumo en el banco, con su proyecto y entidad.

        Usado en el modo 'solo insumos' para comparar el precio ofertado por los
        proveedores contra lo que ya existe en el banco de APUs.
        """
        if not descripcion:
            return []
        objetivo = _tokenizar(descripcion)
        if not objetivo:
            return []
        # Se busca por CUALQUIER palabra significativa (tolera variantes como
        # "minicargador" vs "mini cargador"); luego se re-ordena por similitud y la IA
        # confirma cuáles son realmente el mismo insumo (en el use case).
        palabras = sorted(objetivo, key=len, reverse=True)[:6]
        condiciones = " OR ".join(["insumo_descripcion LIKE %s" for _ in palabras])
        params = [f"%{p}%" for p in palabras]
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                # Se incluyen también insumos SIN precio (existen en el banco aunque no
                # tengan valor); las filas con precio válido se muestran primero.
                cursor.execute(
                    f"""SELECT insumo_descripcion, insumo_unidad, tipo_insumo,
                               rendimiento_insumo, precio_unitario_apu, precio_parcial_apu,
                               nombre_proyecto, entidad, ciudad, contratista,
                               MAX(fecha_aprobacion_apu) AS fecha
                        FROM apus
                        WHERE {condiciones}
                        GROUP BY insumo_descripcion, insumo_unidad, tipo_insumo,
                                 rendimiento_insumo, precio_unitario_apu, precio_parcial_apu,
                                 nombre_proyecto, entidad, ciudad, contratista
                        ORDER BY (precio_unitario_apu IS NULL OR precio_unitario_apu <= 0) ASC,
                                 precio_unitario_apu DESC
                        LIMIT 250""",
                    params,
                )
                filas = cursor.fetchall()
                if not filas:
                    return []
                for f in filas:
                    f["_score"] = _similitud_tokens(objetivo, _tokenizar(f.get("insumo_descripcion", "")))
                filas = [f for f in filas if f["_score"] > 0]
                # Prioriza las referencias CON valor, luego por similitud y precio.
                filas.sort(
                    key=lambda f: (
                        1 if (f.get("precio_unitario_apu") and float(f["precio_unitario_apu"]) > 0) else 0,
                        f["_score"],
                        float(f.get("precio_unitario_apu") or 0),
                    ),
                    reverse=True,
                )
                top = filas[:max_ref]
                for f in top:
                    f["similitud"] = round(f.pop("_score", 0.0), 3)
                return top

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
                    (proyecto_id, item_code, descripcion, unidad, 0,
                     valor_unitario, 0, solicitud_id),
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

    def buscar_apus_similares(self, descripcion: str, max_candidatos: int = 5, max_insumos: int = 40) -> list:
        """Devuelve los APUs del banco más parecidos al ítem cotizado.

        Cada candidato es un APU COMPLETO (no una fila de insumo suelta): trae el
        proyecto, entidad, ciudad, contratista y precio del ítem, más la lista de
        sus insumos (descripción, unidad, rendimiento y precios). El ranking usa
        similitud de tokens (Jaccard) sobre la descripción del ítem.
        """
        if not descripcion:
            return []
        palabras = [p for p in descripcion.split() if len(p) > 3][:6]
        if not palabras:
            return []
        condiciones = " OR ".join(["items_descripcion LIKE %s" for _ in palabras])
        params = [f"%{p}%" for p in palabras]

        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                # Paso 1: cabeceras de APUs candidatos (un registro por APU del banco).
                cursor.execute(
                    f"""SELECT numero_contrato, link_documento, item, items_descripcion, item_unidad,
                               nombre_proyecto, entidad, ciudad, contratista,
                               MAX(precio_unitario) AS precio_unitario,
                               MAX(precio_unitario_sin_aiu) AS precio_unitario_sin_aiu,
                               MAX(fecha_aprobacion_apu) AS fecha,
                               COUNT(*) AS num_insumos
                        FROM apus
                        WHERE ({condiciones}) AND precio_unitario IS NOT NULL
                        GROUP BY numero_contrato, link_documento, item, items_descripcion,
                                 item_unidad, nombre_proyecto, entidad, ciudad, contratista
                        ORDER BY num_insumos DESC
                        LIMIT 80""",
                    params,
                )
                candidatos = cursor.fetchall()
                if not candidatos:
                    return []

                objetivo = _tokenizar(descripcion)
                for c in candidatos:
                    c["_score"] = _similitud_tokens(objetivo, _tokenizar(c.get("items_descripcion", "")))
                candidatos = [c for c in candidatos if c["_score"] > 0]
                candidatos.sort(key=lambda c: (c["_score"], c.get("num_insumos", 0)), reverse=True)
                top = candidatos[:max_candidatos]

                # Paso 2: insumos de cada APU candidato (NULL-safe con <=> por si hay campos vacíos).
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
                    c["similitud"] = round(c.pop("_score", 0.0), 3)
                return top


analisis_repo = AnalisisMySQLRepository()