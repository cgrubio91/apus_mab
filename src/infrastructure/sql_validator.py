import re
import logging
import unicodedata
from typing import Tuple

log = logging.getLogger("mapus.infrastructure.sql")

try:
    import sqlparse
    from sqlparse.sql import Identifier, IdentifierList, TokenList
    from sqlparse.tokens import DDL, DML, Keyword
    HAS_SQLPARSE = True
except ImportError:
    HAS_SQLPARSE = False
    log.info("sqlparse no disponible, usando validación regex")

ALLOWED_TABLES = {"apus"}

DANGEROUS_FUNCTIONS = re.compile(
    r"\b(pg_sleep|pg_read_file|pg_ls_dir|pg_stat_file|"
    r"pg_get_keywords|current_setting|set_config|"
    r"lo_import|lo_export|copy|pg_terminate_backend|"
    r"pg_cancel_backend|dblink|pg_write_file|"
    r"pg_execute|xp_cmdshell|exec|execute\s*\()",
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


def normalize_accents(text: str) -> str:
    """Strip diacritics/accents from text for accent-insensitive ILIKE matching.
    Ej: 'diámetro' -> 'diametro', 'épocas' -> 'epocas', 'CAÑO' -> 'CANO'
    """
    nfkd = unicodedata.normalize('NFKD', text)
    return nfkd.encode('ascii', 'ignore').decode('ascii')


def _normalize_sql_accents(sql: str) -> str:
    """Remove accents from string literals in SQL for accent-insensitive matching.
    Only affects content inside single quotes (ILIKE patterns), not SQL keywords.
    """
    def _replace_literal(match):
        quote = match.group(1)  # opening quote
        content = match.group(2)  # content between quotes
        return quote + normalize_accents(content) + quote

    return re.sub(r"(')([^']*)(')", _replace_literal, sql)


def _adjust_limit(sql: str) -> str:
    match = re.search(r"\blimit\s+(\d+)", sql, re.IGNORECASE)
    if match:
        limit_value = int(match.group(1))
        if limit_value > MAX_LIMIT:
            sql = re.sub(r"\blimit\s+\d+", f"LIMIT {MAX_LIMIT}", sql, flags=re.IGNORECASE)
    else:
        sql += f" LIMIT {MAX_LIMIT}"
    return sql


def _regex_validate(sql: str) -> Tuple[bool, str]:
    if not ALLOWED_SQL_START.match(sql):
        return False, "Solo se permiten consultas SELECT o WITH"

    if DANGEROUS_SQL.search(sql):
        return False, "SQL peligroso detectado"

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

    return True, _adjust_limit(sql)


def _sqlparse_validate(sql: str) -> Tuple[bool, str]:
    parsed = sqlparse.parse(sql)
    if not parsed:
        return False, "SQL no pudo ser parseado"

    stmt = parsed[0]
    stmt_type = stmt.get_type()

    if stmt_type == "SELECT":
        has_limit = False
        for token in stmt.tokens:
            if token.ttype is Keyword and token.value.upper() == "LIMIT":
                has_limit = True
                break
        return True, _adjust_limit(sql)
    
    for token in stmt.tokens:
        if token.ttype in (DDL, DML):
            return False, f"Solo se permiten consultas SELECT. Detectado: {token.value.upper()}"
        if token.ttype is Keyword and token.value.upper() in (
            "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "CREATE",
            "ALTER", "EXECUTE", "EXEC", "GRANT", "REVOKE", "MERGE", "COPY",
            "VACUUM", "ANALYZE", "NOTIFY", "LISTEN", "CALL",
        ):
            return False, f"Solo se permiten consultas SELECT. Detectado: {token.value.upper()}"

    return True, _adjust_limit(sql)


def validate_readonly_query(sql: str) -> Tuple[bool, str]:
    if not sql or not sql.strip():
        return False, "SQL vacío"

    sql = sql.strip()
    sql = _normalize_sql_accents(sql)

    if ";" in sql.rstrip(";"):
        return False, "No se permiten múltiples statements"

    if DANGEROUS_FUNCTIONS.search(sql):
        return False, "Funciones peligrosas no permitidas"

    if HAS_SQLPARSE:
        valid, result = _sqlparse_validate(sql)
    else:
        valid, result = _regex_validate(sql)

    if not valid:
        return valid, result

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

    has_star = re.search(
        r"select\s+\*\s+from\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        sql,
        re.IGNORECASE,
    )
    if has_star and has_star.group(1).lower() in ALLOWED_TABLES:
        return False, "SELECT * no permitido sobre tablas reales"

    return True, result
