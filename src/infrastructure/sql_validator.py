"""
Infrastructure: SQL Read-Only Validator
Ensures only SELECT/WITH queries against authorized tables.
"""

import re
import logging
from typing import Tuple

log = logging.getLogger("mapus.infrastructure.sql")

ALLOWED_TABLES = {"apus"}

ALLOWED_COLUMNS = {
    "fecha_aprobacion_apu", "fecha_analisis_apu", "ciudad", "pais", "entidad",
    "contratista", "nombre_proyecto", "numero_contrato", "item", "items_descripcion",
    "item_unidad", "precio_unitario", "precio_unitario_sin_aiu", "codigo_insumo",
    "tipo_insumo", "insumo_descripcion", "insumo_unidad", "rendimiento_insumo",
    "precio_unitario_apu", "precio_parcial_apu", "observacion", "link_documento",
}

DANGEROUS_FUNCTIONS = re.compile(
    r"\b(pg_sleep|pg_read_file|pg_ls_dir|pg_stat_file|"
    r"pg_get_keywords|current_setting|set_config|"
    r"lo_import|lo_export|copy|pg_terminate_backend|"
    r"pg_cancel_backend|dblink|pg_write_file)\s*\(",
    re.IGNORECASE,
)

DANGEROUS_SQL = re.compile(
    r"""
    \b(
    drop|truncate|delete|insert|update|
    alter|create|execute|exec|
    grant|revoke|copy|
    vacuum|analyze|merge|listen|notify
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

ALLOWED_SQL_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

SELECT_STAR_FROM_REAL = re.compile(
    r"select\s+\*\s+from\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)

MAX_LIMIT = 20


def validate_readonly_query(sql: str) -> Tuple[bool, str]:
    if not sql or not sql.strip():
        return False, "SQL vacío"

    sql = sql.strip()

    if ";" in sql.rstrip(";"):
        return False, "No se permiten múltiples statements"

    if not ALLOWED_SQL_START.match(sql):
        return False, "Solo se permiten consultas SELECT o WITH"

    if DANGEROUS_SQL.search(sql):
        return False, "SQL peligroso detectado"

    if DANGEROUS_FUNCTIONS.search(sql):
        return False, "Funciones peligrosas no permitidas"

    cte_names = set(
        match.lower()
        for match in re.findall(
            r"(?:with|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+as",
            sql,
            re.IGNORECASE,
        )
    )

    tables = re.findall(
        r"(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        sql,
        re.IGNORECASE,
    )

    for table in tables:
        table_lower = table.lower()
        if table_lower not in ALLOWED_TABLES and table_lower not in cte_names:
            return False, f"Tabla no autorizada: {table}"

    for table in SELECT_STAR_FROM_REAL.findall(sql):
        if table.lower() in ALLOWED_TABLES:
            return False, "SELECT * no permitido sobre tablas reales"

    has_limit = re.search(r"\blimit\s+(\d+)", sql, re.IGNORECASE)
    if has_limit:
        limit_value = int(has_limit.group(1))
        if limit_value > MAX_LIMIT:
            sql = re.sub(r"\blimit\s+\d+", f"LIMIT {MAX_LIMIT}", sql, flags=re.IGNORECASE)
    else:
        sql += f" LIMIT {MAX_LIMIT}"

    return True, sql
