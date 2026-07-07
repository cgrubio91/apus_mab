"""
Infrastructure: APU Repository Implementation (MySQL)
Bulk insert, query, filter, delete — all db interactions for APU records.
"""

import logging
import re
import unicodedata
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional

import mysql.connector

from src.infrastructure.database.connection import get_db_connection

log = logging.getLogger("mapus.infrastructure.apu_repo")

MAX_ERRORS_RETAINED = 100
BULK_PAGE_SIZE = 500
STREAM_BATCH_SIZE = 200

TIPO_INSUMO_MAP = {
    "equipo": "Equipos",
    "i. equipo": "Equipos",
    "herramienta": "Herramienta",
    "herramienta menor": "Herramienta",
    "material": "Materiales",
    "materiales": "Materiales",
    "ii. materiales": "Materiales",
    "mano de obra": "Mano de obra",
    "iv. mano de obra": "Mano de obra",
    "transporte": "Transporte",
    "transportes": "Transporte",
    "iii. transportes": "Transporte",
    "indirecto": "Indirectos",
    "indirectos": "Indirectos",
    "administracion": "Indirectos",
    "aiu": "Indirectos",
    "costo directo": "Indirectos",
    "costos indirectos": "Indirectos",
    "directo": "Indirectos",
    "imprevistos": "Indirectos",
    "utilidad": "Indirectos",
    "v. costos indirectos": "Indirectos",
}


def _normalize_tipo_insumo(val: str | None) -> str | None:
    if val is None:
        return None
    key = val.strip().lower()
    key = unicodedata.normalize("NFKC", key)
    return TIPO_INSUMO_MAP.get(key, val)


def _std_field(item: Dict[str, Any], field_name: str, is_numeric: bool = False, is_date: bool = False) -> Any:
    val = item.get(field_name)
    if val in ("–", "—", "-", "", None):
        return None
    if isinstance(val, str):
        val = unicodedata.normalize("NFKC", val).strip()
        if val in ("–", "—", "-", "", ".") or val.lower() in ("null", "none"):
            return None
        if is_date:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", val):
                return None
    if is_numeric and val is not None:
        try:
            return Decimal(str(val))
        except (ValueError, TypeError):
            return None
    return val


class ApuMySQLRepository:

    _allowed_sort_fields = {
        "id", "nombre_proyecto", "ciudad", "precio_unitario",
        "contratista", "entidad", "fecha_aprobacion_apu", "precio_parcial_apu",
    }
    _max_limit = 500

    # ------------------------------------------------------------------
    # INSERT
    # ------------------------------------------------------------------

    def insert_apus_batch(self, apus_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not apus_list:
            return {"status": "success", "count": 0, "duplicates": 0, "errors": []}

        sql = """
            INSERT IGNORE INTO apus (
                fecha_aprobacion_apu, fecha_analisis_apu,
                ciudad, pais, entidad, contratista, nombre_proyecto,
                numero_contrato, item, items_descripcion, item_unidad,
                precio_unitario, precio_unitario_sin_aiu,
                codigo_insumo, tipo_insumo, insumo_descripcion,
                insumo_unidad, rendimiento_insumo,
                precio_unitario_apu, precio_parcial_apu,
                observacion, link_documento
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        tuple_data = []
        for item in apus_list:
            row = (
                _std_field(item, "fecha_aprobacion_apu", is_date=True),
                _std_field(item, "fecha_analisis_apu", is_date=True),
                _std_field(item, "ciudad"),
                _std_field(item, "pais"),
                _std_field(item, "entidad"),
                _std_field(item, "contratista"),
                _std_field(item, "nombre_proyecto"),
                _std_field(item, "numero_contrato"),
                _std_field(item, "item"),
                _std_field(item, "items_descripcion"),
                _std_field(item, "item_unidad"),
                _std_field(item, "precio_unitario", is_numeric=True),
                _std_field(item, "precio_unitario_sin_aiu", is_numeric=True),
                _std_field(item, "codigo_insumo"),
                _normalize_tipo_insumo(_std_field(item, "tipo_insumo")),
                _std_field(item, "insumo_descripcion"),
                _std_field(item, "insumo_unidad"),
                _std_field(item, "rendimiento_insumo", is_numeric=True),
                _std_field(item, "precio_unitario_apu", is_numeric=True),
                _std_field(item, "precio_parcial_apu", is_numeric=True),
                _std_field(item, "observacion"),
                _std_field(item, "link_documento"),
            )
            tuple_data.append(row)

        total_requested = len(tuple_data)

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.executemany(sql, tuple_data)
                    conn.commit()
                    inserted_count = cursor.rowcount
                    return {
                        "status": "success",
                        "count": inserted_count,
                        "duplicates": total_requested - inserted_count,
                        "errors": [],
                    }
        except mysql.connector.Error as e:
            return self._fallback_insert(apus_list, e)

    def _fallback_insert(self, apus_list: list, original_error: Exception) -> dict:
        error_msg = f"Database bulk execution failed: {original_error}"
        log.warning("Fallback to row-by-row insert: %s", error_msg)
        inserted_count = 0
        db_errors = [error_msg]
        single_sql = """
            INSERT IGNORE INTO apus (
                fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad, contratista,
                nombre_proyecto, numero_contrato, item, items_descripcion, item_unidad,
                precio_unitario, precio_unitario_sin_aiu, codigo_insumo, tipo_insumo,
                insumo_descripcion, insumo_unidad, rendimiento_insumo, precio_unitario_apu,
                precio_parcial_apu, observacion, link_documento
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    for item in apus_list:
                        row = (
                            _std_field(item, "fecha_aprobacion_apu", is_date=True),
                            _std_field(item, "fecha_analisis_apu", is_date=True),
                            _std_field(item, "ciudad"),
                            _std_field(item, "pais"),
                            _std_field(item, "entidad"),
                            _std_field(item, "contratista"),
                            _std_field(item, "nombre_proyecto"),
                            _std_field(item, "numero_contrato"),
                            _std_field(item, "item"),
                            _std_field(item, "items_descripcion"),
                            _std_field(item, "item_unidad"),
                            _std_field(item, "precio_unitario", is_numeric=True),
                            _std_field(item, "precio_unitario_sin_aiu", is_numeric=True),
                            _std_field(item, "codigo_insumo"),
                            _std_field(item, "tipo_insumo"),
                            _std_field(item, "insumo_descripcion"),
                            _std_field(item, "insumo_unidad"),
                            _std_field(item, "rendimiento_insumo", is_numeric=True),
                            _std_field(item, "precio_unitario_apu", is_numeric=True),
                            _std_field(item, "precio_parcial_apu", is_numeric=True),
                            _std_field(item, "observacion"),
                            _std_field(item, "link_documento"),
                        )
                        try:
                            cursor.execute(single_sql, row)
                            conn.commit()
                            if cursor.rowcount and cursor.rowcount > 0:
                                inserted_count += 1
                        except mysql.connector.Error as row_err:
                            conn.rollback()
                            if len(db_errors) < MAX_ERRORS_RETAINED:
                                db_errors.append(str(row_err))
            return {"status": "success", "count": inserted_count, "duplicates": len(apus_list) - inserted_count, "errors": db_errors[1:]}
        except mysql.connector.Error as fallback_err:
            log.exception("Fallback insert also failed")
            return {"status": "error", "count": inserted_count, "duplicates": 0, "errors": db_errors + [str(fallback_err)]}

    def insert_apus_stream(self, apus_list: list):
        idx = 0
        total = len(apus_list)
        while idx < total:
            batch = apus_list[idx: idx + STREAM_BATCH_SIZE]
            result = self.insert_apus_batch(batch)
            yield {"type": "progress", "inserted": result["count"], "total": total, "errors": result.get("errors", []), "errors_truncated": len(result.get("errors", [])) > MAX_ERRORS_RETAINED}
            idx += STREAM_BATCH_SIZE

    # ------------------------------------------------------------------
    # QUERY
    # ------------------------------------------------------------------

    def get_apus(
        self,
        filters: dict,
        limit: int = 50,
        offset: int = 0,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        search: Optional[str] = None,
    ) -> dict:
        limit = min(max(1, limit), self._max_limit)
        offset = max(0, offset)

        where_clauses = []
        params = []

        text_filters = [
            'nombre_proyecto', 'ciudad', 'items_descripcion', 'insumo_descripcion',
            'tipo_insumo', 'contratista', 'entidad', 'codigo_insumo', 'item',
            'item_unidad', 'insumo_unidad', 'pais', 'numero_contrato',
        ]

        for field in text_filters:
            value = filters.get(field)
            if value:
                where_clauses.append(f"{field} LIKE %s")
                params.append(f"%{str(value).strip()}%")

        if search:
            search_value = f"%{search.strip()}%"
            search_clause = (
                "(nombre_proyecto LIKE %s OR "
                "items_descripcion LIKE %s OR "
                "insumo_descripcion LIKE %s OR "
                "contratista LIKE %s)"
            )
            where_clauses.append(search_clause)
            params.extend([search_value] * 4)

        where_str = " AND ".join(where_clauses)
        where_str = f"WHERE {where_str}" if where_str else ""

        sort_column = "id"
        if sort_by:
            normalized = sort_by.strip().lower()
            if normalized in self._allowed_sort_fields:
                sort_column = normalized

        order_direction = "DESC" if str(sort_order).lower() == "desc" else "ASC"

        try:
            with get_db_connection() as conn:
                with conn.cursor(dictionary=True) as cursor:
                    count_query = f"SELECT COUNT(*) as total FROM apus {where_str}"
                    cursor.execute(count_query, params)
                    total = cursor.fetchone()['total']

                    query = f"""
                        SELECT fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad,
                               contratista, nombre_proyecto, numero_contrato, item, items_descripcion,
                               item_unidad, precio_unitario, precio_unitario_sin_aiu, codigo_insumo,
                               tipo_insumo, insumo_descripcion, insumo_unidad, rendimiento_insumo,
                               precio_unitario_apu, precio_parcial_apu, observacion, link_documento
                        FROM apus
                        {where_str}
                        ORDER BY {sort_column} {order_direction}
                        LIMIT %s OFFSET %s
                    """
                    cursor.execute(query, params + [limit, offset])
                    results = cursor.fetchall()

                    return {
                        "success": True,
                        "count": len(results),
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "data": results,
                    }
        except mysql.connector.Error:
            log.exception("Database error in get_apus")
            raise

    def get_unique_projects(self) -> list[str]:
        query = "SELECT DISTINCT nombre_proyecto FROM apus WHERE nombre_proyecto IS NOT NULL ORDER BY nombre_proyecto"
        try:
            with get_db_connection() as conn:
                with conn.cursor(dictionary=True) as cursor:
                    cursor.execute(query)
                    return [r['nombre_proyecto'] for r in cursor.fetchall()]
        except mysql.connector.Error:
            log.exception("Database error in get_unique_projects")
            raise

    def get_dashboard_stats(self) -> dict:
        summary_query = """
            SELECT
                COUNT(*) as total_apus,
                COUNT(DISTINCT nombre_proyecto) as total_projects,
                COUNT(DISTINCT ciudad) as total_cities,
                CAST(
                    SUM(CASE WHEN item IS NOT NULL AND items_descripcion IS NOT NULL
                             AND codigo_insumo IS NOT NULL AND precio_unitario IS NOT NULL
                        THEN 1 ELSE 0 END) AS DECIMAL(30,10)
                ) / NULLIF(COUNT(*), 0) * 100 as completitud_datos
            FROM apus
        """
        breakdown_query = """
            SELECT tipo_insumo, COUNT(*) as apu_count
            FROM apus GROUP BY tipo_insumo ORDER BY apu_count DESC
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor(dictionary=True) as cursor:
                    cursor.execute(summary_query)
                    summary = cursor.fetchone() or {}
                    cursor.execute(breakdown_query)
                    rows = cursor.fetchall()
                    breakdown = {r['tipo_insumo'] or 'Sin tipo': r['apu_count'] for r in rows}
                    return {
                        'total_apus': summary.get('total_apus', 0),
                        'total_projects': summary.get('total_projects', 0),
                        'total_cities': summary.get('total_cities', 0),
                        'completitud_datos': round(float(summary.get('completitud_datos') or 0.0), 1),
                        'apus_por_tipo_insumo': breakdown,
                    }
        except mysql.connector.Error:
            log.exception("Database error in get_dashboard_stats")
            raise

    def get_filter_options(self) -> dict[str, list[str]]:
        query = """
            SELECT
                COALESCE(NULLIF(GROUP_CONCAT(DISTINCT ciudad), ''), '[]') as ciudad,
                COALESCE(NULLIF(GROUP_CONCAT(DISTINCT entidad), ''), '[]') as entidad,
                COALESCE(NULLIF(GROUP_CONCAT(DISTINCT contratista), ''), '[]') as contratista,
                COALESCE(NULLIF(GROUP_CONCAT(DISTINCT tipo_insumo), ''), '[]') as tipo_insumo,
                COALESCE(NULLIF(GROUP_CONCAT(DISTINCT pais), ''), '[]') as pais
            FROM apus;
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor(dictionary=True) as cursor:
                    cursor.execute(query)
                    row = cursor.fetchone()
                    if not row:
                        return {"ciudad": [], "entidad": [], "contratista": [], "tipo_insumo": [], "pais": []}
                    options = {
                        "ciudad": sorted(row["ciudad"].split(",")) if row["ciudad"] != "[]" else [],
                        "entidad": sorted(row["entidad"].split(",")) if row["entidad"] != "[]" else [],
                        "contratista": sorted(row["contratista"].split(",")) if row["contratista"] != "[]" else [],
                        "tipo_insumo": sorted(row["tipo_insumo"].split(",")) if row["tipo_insumo"] != "[]" else [],
                        "pais": sorted(row["pais"].split(",")) if row["pais"] != "[]" else [],
                    }
                    return options
        except mysql.connector.Error:
            log.exception("Database error in get_filter_options")
            raise

    def delete_project_apus(self, nombre_proyecto: str) -> dict:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM apus WHERE nombre_proyecto = %s", (nombre_proyecto,))
                    count = cursor.rowcount
                    conn.commit()
                    return {"success": True, "deleted": count, "message": f"Se eliminaron {count} APUs de {nombre_proyecto}."}
        except mysql.connector.Error:
            log.exception("Database error deleting project: %s", nombre_proyecto)
            raise


apu_repo = ApuMySQLRepository()

# Module-level convenience functions
def insert_apus_batch(apus_list): return apu_repo.insert_apus_batch(apus_list)
def insert_apus_stream(apus_list): return apu_repo.insert_apus_stream(apus_list)
def get_unique_projects(): return apu_repo.get_unique_projects()
def get_apus(*args, **kwargs): return apu_repo.get_apus(*args, **kwargs)
def get_dashboard_stats(): return apu_repo.get_dashboard_stats()
def delete_project_apus(nombre_proyecto): return apu_repo.delete_project_apus(nombre_proyecto)