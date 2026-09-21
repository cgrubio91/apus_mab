"""
Infrastructure: Análisis APU Repository Implementation (MySQL)

La clase AnalisisMySQLRepository vive aquí con la misma API pública. Los
helpers de emparejamiento por tokens y las búsquedas sobre el banco viven en
analisis_matching y se re-exportan para compatibilidad de importes.
"""

import json
import logging
from typing import Optional

from src.infrastructure.database.connection import execute_query, get_db_connection
from src.infrastructure.database.repositories import analisis_matching as _matching
from src.infrastructure.database.repositories.analisis_matching import (
    _PREFIJOS_COMPUESTOS,
    _STOPWORDS,
    _TOKENS_TECNICOS,
    _coincidencia_compuesta,
    _coincidencia_palabra_completa,
    _expandir_compuestos,
    _normalizar,
    _similitud_tokens,
    _token_util,
    _tokenizar,
)

log = logging.getLogger("mapus.infrastructure.analisis_repo")


def _json_columna(valor) -> Optional[str]:
    """Serializa un list/dict para una columna JSON de MySQL (los strings se pasan tal cual)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False, default=str)
    return str(valor)


__all__ = [
    "AnalisisMySQLRepository",
    "analisis_repo",
    "_STOPWORDS",
    "_TOKENS_TECNICOS",
    "_PREFIJOS_COMPUESTOS",
    "_normalizar",
    "_token_util",
    "_tokenizar",
    "_similitud_tokens",
    "_expandir_compuestos",
    "_coincidencia_compuesta",
    "_coincidencia_palabra_completa",
]

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
                                precio_banco, rendimiento_banco, fuente_precio,
                                grupo_proveedores, proveedores_sugeridos)
                               VALUES (%s, 1, 'Estructura Constructor', %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s, %s, %s, %s, %s, %s)""",
                            (solicitud_id, f.get("item"), f.get("items_descripcion"), f.get("item_unidad"),
                             f.get("codigo_insumo"), f.get("insumo_descripcion"), f.get("insumo_unidad"),
                             f.get("rendimiento_insumo"), f.get("tipo_insumo"),
                             f.get("precio_banco"), f.get("rendimiento_banco"), f.get("fuente_precio"),
                             f.get("grupo_proveedores"), _json_columna(f.get("proveedores_sugeridos"))),
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
                            precio_banco, rendimiento_banco, fuente_precio,
                            grupo_proveedores, proveedores_sugeridos)
                           VALUES (%s, 1, 'Estructura Constructor', %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s, %s, %s, %s, %s, %s)""",
                        (solicitud_id, fila.get("item"), fila.get("items_descripcion"), fila.get("item_unidad"),
                         fila.get("codigo_insumo"), fila.get("insumo_descripcion"), fila.get("insumo_unidad"),
                         fila.get("rendimiento_insumo"), fila.get("tipo_insumo"),
                         fila.get("precio_banco"), fila.get("rendimiento_banco"), fila.get("fuente_precio"),
                         fila.get("grupo_proveedores"), _json_columna(fila.get("proveedores_sugeridos"))),
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

    def get_solicitudes(self, estado: Optional[str] = None, origen: Optional[str] = None) -> list:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                base_query = """
                    SELECT sa.*,
                           (SELECT items_descripcion FROM solicitud_insumos
                            WHERE solicitud_id = sa.id ORDER BY grupo_cotizacion, id LIMIT 1) as primer_item,
                           (SELECT COUNT(*) FROM solicitud_insumos WHERE solicitud_id = sa.id) as total_items
                    FROM solicitudes_apu sa
                """
                clauses, params = [], []
                if estado:
                    clauses.append("sa.estado = %s")
                    params.append(estado)
                if origen:
                    clauses.append("sa.origen = %s")
                    params.append(origen)
                where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
                cursor.execute(base_query + where + " ORDER BY sa.created_at DESC", tuple(params))
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
        """Delega en analisis_matching.buscar_insumos_candidatos (misma firma)."""
        return _matching.buscar_insumos_candidatos(descripcion, max_desc=max_desc)

    def referencias_de_descripciones(self, descripciones: list, max_total: int = 12, por_desc: int = 4) -> list:
        """Delega en analisis_matching.referencias_de_descripciones (misma firma)."""
        return _matching.referencias_de_descripciones(descripciones, max_total=max_total, por_desc=por_desc)

    def buscar_insumos_similares(self, descripcion: str, max_ref: int = 12) -> list:
        """Delega en analisis_matching.buscar_insumos_similares (misma firma)."""
        return _matching.buscar_insumos_similares(descripcion, max_ref=max_ref)

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
        """Delega en analisis_matching.buscar_en_banco (misma firma)."""
        return _matching.buscar_en_banco(descripcion)

    def buscar_apus_similares(self, descripcion: str, insumos_desc: Optional[list] = None,
                              max_candidatos: int = 5, max_insumos: int = 40) -> list:
        """Delega en analisis_matching.buscar_apus_similares (misma firma)."""
        return _matching.buscar_apus_similares(
            descripcion, insumos_desc=insumos_desc, max_candidatos=max_candidatos, max_insumos=max_insumos
        )

    def eliminar_solicitud(self, solicitud_id: int) -> bool:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM aprendizaje_rechazos WHERE analisis_id IN (SELECT id FROM analisis_apu WHERE solicitud_id = %s)",
                        (solicitud_id,),
                    )
                    cursor.execute("DELETE FROM notificaciones WHERE solicitud_id = %s", (solicitud_id,))
                    cursor.execute("DELETE FROM solicitudes_apu WHERE id = %s", (solicitud_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception:
            log.exception("Error eliminando solicitud %d", solicitud_id)
            raise

    def eliminar_solicitudes_lote(self, solicitud_ids: list[int]) -> int:
        if not solicitud_ids:
            return 0
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    format_strings = ",".join(["%s"] * len(solicitud_ids))
                    cursor.execute(
                        f"DELETE FROM aprendizaje_rechazos WHERE analisis_id IN (SELECT id FROM analisis_apu WHERE solicitud_id IN ({format_strings}))",
                        tuple(solicitud_ids),
                    )
                    cursor.execute(
                        f"DELETE FROM notificaciones WHERE solicitud_id IN ({format_strings})",
                        tuple(solicitud_ids),
                    )
                    cursor.execute(
                        f"DELETE FROM solicitudes_apu WHERE id IN ({format_strings})",
                        tuple(solicitud_ids),
                    )
                    afectadas = cursor.rowcount
                    conn.commit()
                    return afectadas
        except Exception:
            log.exception("Error eliminando lote de solicitudes %s", solicitud_ids)
            raise


analisis_repo = AnalisisMySQLRepository()
