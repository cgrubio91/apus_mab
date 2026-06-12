"""
Pytest configuration and fixtures for MAPUS integration tests.
Requires a PostgreSQL database specified by TEST_DB_* environment variables.
Tests are automatically skipped when no database is available.
"""

import os
import sys
import logging

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.disable(logging.CRITICAL)

# ── Test environment defaults ───────────────────────────────────────
os.environ.setdefault("AI_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

TEST_DB_CONFIG = {
    "host": os.getenv("TEST_DB_HOST") or os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("TEST_DB_PORT") or os.getenv("DB_PORT", "5432")),
    "user": os.getenv("TEST_DB_USER") or os.getenv("DB_USER", "postgres"),
    "password": os.getenv("TEST_DB_PASSWORD") or os.getenv("DB_PASSWORD", "postgres"),
    "dbname": os.getenv("TEST_DB_NAME") or f"test_{os.getenv('DB_NAME', 'mapus')}",
}

for key, val in TEST_DB_CONFIG.items():
    env_key = f"DB_{key.upper()}"
    os.environ.setdefault(env_key, str(val))

os.environ.setdefault("DB_SSLMODE", "disable")


def db_available() -> bool:
    """Check if the test database is reachable."""
    try:
        import psycopg2
        conn = psycopg2.connect(**TEST_DB_CONFIG, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


def _init_test_db():
    """Apply schema to the test database."""
    from db_schema import ensure_schema
    ensure_schema()


@pytest.fixture(scope="session")
def test_db():
    """Initialize test database schema once per session."""
    if not db_available():
        pytest.skip("PostgreSQL test database not available")
    _init_test_db()
    yield


@pytest.fixture
def seed_data(test_db):
    """Insert sample APU data before each test and clean up after."""
    from db_config import execute_query

    sample_rows = [
        {
            "nombre_proyecto": "Proyecto Test Alpha",
            "ciudad": "Bogotá",
            "pais": "Colombia",
            "entidad": "IDU",
            "contratista": "Constructora Beta",
            "item": "1.1",
            "items_descripcion": "Excavación manual",
            "item_unidad": "M3",
            "precio_unitario": 85000.00,
            "codigo_insumo": "EXC-001",
            "tipo_insumo": "Mano de obra",
            "insumo_descripcion": "Excavación manual en terreno común",
            "insumo_unidad": "M3",
            "rendimiento_insumo": 1.00,
            "precio_unitario_apu": 85000.00,
            "precio_parcial_apu": 85000.00,
            "numero_contrato": "CT-2024-001",
            "link_documento": "test_alpha.pdf",
            "fecha_aprobacion_apu": "2024-01-15",
        },
        {
            "nombre_proyecto": "Proyecto Test Alpha",
            "ciudad": "Bogotá",
            "pais": "Colombia",
            "entidad": "IDU",
            "contratista": "Constructora Beta",
            "item": "1.2",
            "items_descripcion": "Concreto 3000 psi",
            "item_unidad": "M3",
            "precio_unitario": 520000.00,
            "codigo_insumo": "CON-001",
            "tipo_insumo": "Materiales",
            "insumo_descripcion": "Concreto 3000 psi incluido suministro",
            "insumo_unidad": "M3",
            "rendimiento_insumo": 1.00,
            "precio_unitario_apu": 520000.00,
            "precio_parcial_apu": 520000.00,
            "numero_contrato": "CT-2024-001",
            "link_documento": "test_alpha.pdf",
        },
        {
            "nombre_proyecto": "Proyecto Test Gamma",
            "ciudad": "Medellín",
            "pais": "Colombia",
            "entidad": "Metro de Medellín",
            "contratista": "Constructora Gamma SA",
            "item": "2.1",
            "items_descripcion": "Acero de refuerzo 6000 psi",
            "item_unidad": "KG",
            "precio_unitario": 12500.00,
            "codigo_insumo": "ACE-001",
            "tipo_insumo": "Materiales",
            "insumo_descripcion": "Acero de refuerzo fy=60000 psi",
            "insumo_unidad": "KG",
            "rendimiento_insumo": 1.00,
            "precio_unitario_apu": 12500.00,
            "precio_parcial_apu": 12500.00,
            "numero_contrato": "CT-2024-002",
            "link_documento": "test_gamma.pdf",
        },
    ]

    columns = list(sample_rows[0].keys())
    placeholders = ", ".join(f"%({k})s" for k in columns)
    col_names = ", ".join(columns)

    for row in sample_rows:
        execute_query(
            f"INSERT INTO apus ({col_names}) VALUES ({placeholders})",
            row,
            fetch=False,
        )

    yield

    execute_query("DELETE FROM apus", fetch=False)


@pytest.fixture
def client(seed_data):
    """FastAPI TestClient with seeded data."""
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        yield c
