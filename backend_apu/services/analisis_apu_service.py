"""
Análisis APU Service
====================
Business logic for APU analysis, AI comparison with bank,
approval workflow, and rejection learning.
"""

import json
import logging
from datetime import date, timedelta
from typing import Optional

from db_config import get_db_connection, execute_query
from psycopg2.extras import RealDictCursor

from .analisis_apu_ai import analisis_con_ia, generar_resumen_ia

log = logging.getLogger("mapus.analisis")

ESTADOS = [
    "pendiente_analisis",
    "analizado",
    "preaprobado",
    "rechazado",
    "nuevas_cotizaciones",
    "aprobado_subgerente",
    "aprobado_legal",
]


class AnalisisApuService:

    def _extraer_campo_comun(self, insumos: list, campo: str) -> Optional[str]:
        valores = [
            str(ins.get(campo, "")).strip()
            for ins in insumos
            if ins.get(campo)
        ]
        if valores:
            from collections import Counter
            return Counter(valores).most_common(1)[0][0]
        return None

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
                           VALUES (%s, %s, %s, 'pendiente_analisis')
                           RETURNING id""",
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
                                (
                                    solicitud_id,
                                    grupo_idx,
                                    nombre_archivo,
                                    ins.get("item"),
                                    ins.get("items_descripcion"),
                                    ins.get("item_unidad"),
                                    ins.get("precio_unitario"),
                                    ins.get("codigo_insumo"),
                                    ins.get("insumo_descripcion"),
                                    ins.get("insumo_unidad"),
                                    ins.get("rendimiento_insumo"),
                                    ins.get("tipo_insumo"),
                                ),
                            )

                    conn.commit()
                    log.info(
                        "Solicitud %d creada: %s - %s (%d archivos, %d insumos)",
                        solicitud_id,
                        contratista,
                        nombre_proyecto,
                        len(grupos_insumos),
                        len(all_insumos),
                    )
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
                            WHERE solicitud_id = sa.id
                            ORDER BY grupo_cotizacion, id LIMIT 1) as primer_item,
                           (SELECT COUNT(*) FROM solicitud_insumos
                            WHERE solicitud_id = sa.id) as total_items
                    FROM solicitudes_apu sa
                """
                if estado:
                    cursor.execute(
                        base_query + " WHERE sa.estado = %s ORDER BY sa.created_at DESC",
                        (estado,),
                    )
                else:
                    cursor.execute(
                        base_query + " ORDER BY sa.created_at DESC"
                    )
                return cursor.fetchall()

    def get_solicitud(self, solicitud_id: int) -> Optional[dict]:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """SELECT * FROM solicitudes_apu WHERE id = %s""", (solicitud_id,)
                )
                solicitud = cursor.fetchone()
                if not solicitud:
                    return None

                cursor.execute(
                    """SELECT * FROM solicitud_insumos WHERE solicitud_id = %s
                       ORDER BY grupo_cotizacion, id""",
                    (solicitud_id,),
                )
                solicitud["insumos"] = cursor.fetchall()

                cursor.execute(
                    """SELECT DISTINCT grupo_cotizacion, nombre_archivo
                       FROM solicitud_insumos
                       WHERE solicitud_id = %s
                       ORDER BY grupo_cotizacion""",
                    (solicitud_id,),
                )
                solicitud["grupos_archivos"] = cursor.fetchall()

                cursor.execute(
                    """SELECT * FROM historial_aprobaciones WHERE solicitud_id = %s ORDER BY created_at""",
                    (solicitud_id,),
                )
                solicitud["historial"] = cursor.fetchall()

                cursor.execute(
                    """SELECT * FROM analisis_apu WHERE solicitud_id = %s""",
                    (solicitud_id,),
                )
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

        return {
            "mejor_grupo": mejor_grupo,
            "grupos": grupos,
            "total_grupos": len(grupos),
        }

    def realizar_analisis(self, solicitud_id: int) -> dict:
        solicitud = self.get_solicitud(solicitud_id)
        if not solicitud:
            raise ValueError(f"Solicitud {solicitud_id} no encontrada")

        insumos = solicitud.get("insumos", [])
        if not insumos:
            raise ValueError("La solicitud no tiene insumos para analizar")

        items_analizados = []
        for ins in insumos:
            resultado = self._analizar_item_con_banco(ins)
            items_analizados.append(resultado)

        comparacion_grupos = self._analizar_mejor_grupo(insumos, items_analizados)
        resumen, recomendacion = generar_resumen_ia(insumos, items_analizados, comparacion_grupos)

        analisis_json = json.dumps({
            "items": items_analizados,
            "comparacion_grupos": comparacion_grupos,
        }, default=str)

        try:
            with get_db_connection() as conn:
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
                    cursor.execute(
                        """UPDATE solicitudes_apu SET estado = 'analizado', updated_at = NOW()
                           WHERE id = %s""",
                        (solicitud_id,),
                    )
                    conn.commit()
        except Exception:
            log.exception("Error guardando análisis")
            raise

        return {
            "solicitud_id": solicitud_id,
            "items_analizados": items_analizados,
            "resumen": resumen,
            "recomendacion": recomendacion,
        }

    def _analizar_item_con_banco(self, ins: dict) -> dict:
        descripcion = ins.get("items_descripcion", "")
        if not descripcion:
            return {
                "item": ins.get("item", ""),
                "descripcion": descripcion,
                "unidad": ins.get("item_unidad", ""),
                "precio_ofertado": float(ins.get("precio_unitario") or 0),
                "mejor_precio_banco": None,
                "diferencia_precio": None,
                "existe_en_banco": False,
                "item_banco_encontrado": None,
                "estructura_insumos_coincide": None,
                "rendimiento_coincide": None,
                "observaciones": "Sin descripción para comparar",
                "recomendacion": "pendiente",
                "grupo_cotizacion": ins.get("grupo_cotizacion", 1),
            }

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                palabras = [p for p in descripcion.split() if len(p) > 3][:5]
                condiciones = " OR ".join(
                    [f"items_descripcion ILIKE %s" for _ in palabras]
                )
                params = [f"%{p}%" for p in palabras]
                params.extend([descripcion[:10]])

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
                banco_records = cursor.fetchall()

        precio_ofertado = float(ins.get("precio_unitario") or 0)
        resultado = {
            "item": ins.get("item", ""),
            "descripcion": descripcion,
            "unidad": ins.get("item_unidad", ""),
            "precio_ofertado": precio_ofertado,
            "mejor_precio_banco": None,
            "diferencia_precio": None,
            "existe_en_banco": len(banco_records) > 0,
            "item_banco_encontrado": None,
            "estructura_insumos_coincide": None,
            "rendimiento_coincide": None,
            "observaciones": "",
            "recomendacion": "pendiente",
            "grupo_cotizacion": ins.get("grupo_cotizacion", 1),
        }

        if banco_records:
            mejor_precio = min(
                float(r.get("precio_unitario") or float("inf"))
                for r in banco_records
                if r.get("precio_unitario") is not None
            )
            resultado["mejor_precio_banco"] = mejor_precio
            resultado["diferencia_precio"] = round(precio_ofertado - mejor_precio, 2)
            resultado["item_banco_encontrado"] = banco_records[0].get("item", "")

        resultado = analisis_con_ia(ins, banco_records, resultado)
        return resultado

    def preaprobar(self, solicitud_id: int, usuario_rol: str, usuario_nombre: str) -> dict:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """UPDATE solicitudes_apu
                           SET estado = 'preaprobado', updated_at = NOW()
                           WHERE id = %s AND estado = 'analizado'""",
                        (solicitud_id,),
                    )
                    if cursor.rowcount == 0:
                        raise ValueError("La solicitud no está en estado 'analizado'")

                    cursor.execute(
                        """INSERT INTO historial_aprobaciones
                           (solicitud_id, accion, responsable_rol, responsable_nombre)
                           VALUES (%s, 'preaprobado', %s, %s)""",
                        (solicitud_id, usuario_rol, usuario_nombre),
                    )

                    cursor.execute(
                        """INSERT INTO historial_aprobaciones
                           (solicitud_id, accion, responsable_rol, responsable_nombre)
                           VALUES (%s, 'pendiente_aprobacion_subgerente', %s, %s)""",
                        (solicitud_id, usuario_rol, usuario_nombre),
                    )
                    conn.commit()
                    return {"success": True, "mensaje": "APU preaprobado. Enviado a subgerente técnico."}
        except ValueError:
            raise
        except Exception:
            log.exception("Error en preaprobación")
            raise

    def rechazar(self, solicitud_id: int, usuario_rol: str, usuario_nombre: str, motivo: str) -> dict:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """SELECT estado FROM solicitudes_apu WHERE id = %s""",
                        (solicitud_id,),
                    )
                    row = cursor.fetchone()
                    if not row:
                        raise ValueError("Solicitud no encontrada")

                    estado_actual = row[0]
                    if estado_actual not in ("analizado", "nuevas_cotizaciones"):
                        raise ValueError(f"No se puede rechazar en estado '{estado_actual}'")

                    fecha_limite = date.today() + timedelta(days=5)
                    cursor.execute(
                        """UPDATE solicitudes_apu
                           SET estado = 'nuevas_cotizaciones',
                               fecha_limite_respuesta = %s,
                               updated_at = NOW()
                           WHERE id = %s""",
                        (fecha_limite, solicitud_id),
                    )

                    cursor.execute(
                        """INSERT INTO historial_aprobaciones
                           (solicitud_id, accion, responsable_rol, responsable_nombre, motivo)
                           VALUES (%s, 'rechazado', %s, %s, %s)""",
                        (solicitud_id, usuario_rol, usuario_nombre, motivo),
                    )

                    cursor.execute(
                        """INSERT INTO aprendizaje_rechazos (analisis_id, motivo_rechazo, contexto)
                           SELECT id, %s, %s FROM analisis_apu WHERE solicitud_id = %s""",
                        (motivo, f"Rechazado por {usuario_rol}: {usuario_nombre}", solicitud_id),
                    )
                    conn.commit()

                    return {
                        "success": True,
                        "mensaje": f"APU rechazado. Se solicitarán nuevas cotizaciones (límite: {fecha_limite}).",
                        "fecha_limite": str(fecha_limite),
                    }
        except ValueError:
            raise
        except Exception:
            log.exception("Error en rechazo")
            raise

    def nuevas_cotizaciones_recibidas(self, solicitud_id: int) -> dict:
        fecha_limite = date.today() + timedelta(days=3)
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """UPDATE solicitudes_apu
                           SET estado = 'analizado',
                               fecha_limite_aprobacion = %s,
                               updated_at = NOW()
                           WHERE id = %s AND estado = 'nuevas_cotizaciones'""",
                        (fecha_limite, solicitud_id),
                    )

                    cursor.execute(
                        """INSERT INTO historial_aprobaciones
                           (solicitud_id, accion, responsable_rol, responsable_nombre)
                           VALUES (%s, 'nuevas_cotizaciones_recibidas', 'contraparte', 'Contraparte')""",
                        (solicitud_id,),
                    )
                    conn.commit()
                    return {
                        "success": True,
                        "mensaje": f"Nuevas cotizaciones registradas. Plazo para aprobar: {fecha_limite}.",
                    }
        except Exception:
            log.exception("Error registrando nuevas cotizaciones")
            raise

    def aprobar_subgerente(self, solicitud_id: int, usuario_rol: str, usuario_nombre: str) -> dict:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """UPDATE solicitudes_apu SET estado = 'aprobado_subgerente', updated_at = NOW()
                           WHERE id = %s AND estado = 'preaprobado'""",
                        (solicitud_id,),
                    )
                    if cursor.rowcount == 0:
                        raise ValueError("La solicitud no está en estado 'preaprobado'")

                    cursor.execute(
                        """INSERT INTO historial_aprobaciones
                           (solicitud_id, accion, responsable_rol, responsable_nombre)
                           VALUES (%s, 'aprobado_subgerente', %s, %s)""",
                        (solicitud_id, usuario_rol, usuario_nombre),
                    )

                    cursor.execute(
                        """INSERT INTO historial_aprobaciones
                           (solicitud_id, accion, responsable_rol, responsable_nombre)
                           VALUES (%s, 'pendiente_firma_legal', 'sistema', 'Sistema')""",
                        (solicitud_id,),
                    )
                    conn.commit()
                    return {"success": True, "mensaje": "Aprobado por subgerente técnico. Enviado para firma legal."}
        except ValueError:
            raise
        except Exception:
            log.exception("Error en aprobación de subgerente")
            raise

    def firmar_legal(self, solicitud_id: int, usuario_rol: str, usuario_nombre: str) -> dict:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """UPDATE solicitudes_apu SET estado = 'aprobado_legal', updated_at = NOW()
                           WHERE id = %s AND estado = 'aprobado_subgerente'""",
                        (solicitud_id,),
                    )
                    if cursor.rowcount == 0:
                        raise ValueError("La solicitud no está en estado 'aprobado_subgerente'")

                    cursor.execute(
                        """INSERT INTO historial_aprobaciones
                           (solicitud_id, accion, responsable_rol, responsable_nombre)
                           VALUES (%s, 'aprobado_legal', %s, %s)""",
                        (solicitud_id, usuario_rol, usuario_nombre),
                    )
                    conn.commit()
                    return {"success": True, "mensaje": "APU aprobado y firmado legalmente. Incorporado al banco de APUs."}
        except ValueError:
            raise
        except Exception:
            log.exception("Error en firma legal")
            raise

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


analisis_apu_service = AnalisisApuService()
