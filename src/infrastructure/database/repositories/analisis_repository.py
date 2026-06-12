"""
Infrastructure: Análisis APU Repository Implementation (PostgreSQL)
"""

import json
import logging
from datetime import date, timedelta
from typing import Optional

from src.infrastructure.database.connection import get_db_connection, execute_query
from psycopg2.extras import RealDictCursor

log = logging.getLogger("mapus.infrastructure.analisis_repo")


class AnalisisPostgresRepository:

    def crear_solicitud(self, grupos_insumos: list[dict]) -> int:
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
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        """INSERT INTO solicitudes_apu (link_documento, contratista, nombre_proyecto, estado)
                           VALUES (%s, %s, %s, 'pendiente_analisis') RETURNING id""",
                        (link_documento, contratista, nombre_proyecto),
                    )
                    solicitud_id = cursor.fetchone()["id"]

                    for grupo in grupos_insumos:
                        grupo_idx = grupo.get("grupo_cotizacion", 1)
                        nombre_archivo = grupo.get("nombre_archivo", "")
                        for ins in grupo.get("insumos", []):
                            cursor.execute(
                                """INSERT INTO solicitud_insumos
                                   (solicitud_id, grupo_cotizacion, nombre_archivo,
                                    item, items_descripcion, item_unidad, precio_unitario,
                                    codigo_insumo, insumo_descripcion, insumo_unidad,
                                    rendimiento_insumo, tipo_insumo)
                                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                                (solicitud_id, grupo_idx, nombre_archivo,
                                 ins.get("item"), ins.get("items_descripcion"),
                                 ins.get("item_unidad"), ins.get("precio_unitario"),
                                 ins.get("codigo_insumo"), ins.get("insumo_descripcion"),
                                 ins.get("insumo_unidad"), ins.get("rendimiento_insumo"),
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
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
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
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
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
                       ON CONFLICT (solicitud_id)
                       DO UPDATE SET analisis_json = EXCLUDED.analisis_json,
                                     resumen = EXCLUDED.resumen,
                                     recomendacion = EXCLUDED.recomendacion""",
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

    def buscar_en_banco(self, descripcion: str) -> list:
        if not descripcion:
            return []
        palabras = [p for p in descripcion.split() if len(p) > 3][:5]
        if not palabras:
            return []
        condiciones = " OR ".join([f"items_descripcion ILIKE %s" for _ in palabras])
        params = [f"%{p}%" for p in palabras]
        params.extend([descripcion[:10]])
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f"""SELECT DISTINCT ON (items_descripcion) item, items_descripcion,
                               item_unidad, precio_unitario, precio_unitario_sin_aiu,
                               rendimiento_insumo, tipo_insumo, codigo_insumo,
                               insumo_descripcion, insumo_unidad
                        FROM apus
                        WHERE ({condiciones} OR items_descripcion ILIKE %s)
                          AND precio_unitario IS NOT NULL
                        ORDER BY items_descripcion, precio_unitario ASC
                        LIMIT 5""",
                    params,
                )
                return cursor.fetchall()


analisis_repo = AnalisisPostgresRepository()
