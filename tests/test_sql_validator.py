import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.infrastructure.sql_validator import validate_readonly_query


def test_valid_select():
    is_valid, sql = validate_readonly_query("SELECT * FROM apus LIMIT 5")
    assert not is_valid  # SELECT * no permitido sobre apus


def test_valid_select_specific_columns():
    is_valid, sql = validate_readonly_query(
        "SELECT nombre_proyecto, ciudad FROM apus WHERE ciudad ILIKE '%bogota%'"
    )
    assert is_valid
    assert "LIMIT 20" in sql or "limit 20" in sql


def test_blocked_drop():
    is_valid, _ = validate_readonly_query("DROP TABLE apus")
    assert not is_valid


def test_blocked_delete():
    is_valid, _ = validate_readonly_query("DELETE FROM apus WHERE id = 1")
    assert not is_valid


def test_blocked_insert():
    is_valid, _ = validate_readonly_query(
        "INSERT INTO apus (ciudad) VALUES ('Bogota')"
    )
    assert not is_valid


def test_blocked_update():
    is_valid, _ = validate_readonly_query(
        "UPDATE apus SET ciudad = 'Medellin' WHERE id = 1"
    )
    assert not is_valid


def test_blocked_alter():
    is_valid, _ = validate_readonly_query("ALTER TABLE apus ADD COLUMN test TEXT")
    assert not is_valid


def test_blocked_pg_sleep():
    is_valid, _ = validate_readonly_query(
        "SELECT pg_sleep(10), nombre_proyecto FROM apus LIMIT 1"
    )
    assert not is_valid


def test_blocked_current_setting():
    is_valid, _ = validate_readonly_query(
        "SELECT current_setting('password') FROM apus LIMIT 1"
    )
    assert not is_valid


def test_blocked_unauthorized_table():
    is_valid, _ = validate_readonly_query(
        "SELECT * FROM pg_class LIMIT 1"
    )
    assert not is_valid


def test_limit_enforcement():
    is_valid, sql = validate_readonly_query(
        "SELECT nombre_proyecto FROM apus WHERE ciudad ILIKE '%test%'"
    )
    assert is_valid
    assert "LIMIT 20" in sql.upper() or "limit 20" in sql


def test_limit_capped():
    is_valid, sql = validate_readonly_query(
        "SELECT nombre_proyecto FROM apus LIMIT 100"
    )
    assert is_valid
    import re
    limit_match = re.search(r"LIMIT\s+(\d+)", sql, re.IGNORECASE)
    assert limit_match
    assert int(limit_match.group(1)) <= 20


def test_with_cte():
    is_valid, sql = validate_readonly_query(
        "WITH project_counts AS (SELECT nombre_proyecto, COUNT(*) as cnt FROM apus GROUP BY nombre_proyecto) SELECT * FROM project_counts ORDER BY cnt DESC"
    )
    assert is_valid


def test_empty_sql():
    is_valid, _ = validate_readonly_query("")
    assert not is_valid


def test_multi_statement():
    is_valid, _ = validate_readonly_query(
        "SELECT * FROM apus; DROP TABLE apus"
    )
    assert not is_valid
