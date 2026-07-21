"""
Pytest configuration and fixtures for MAPUS integration tests.
Requires a MySQL database specified by TEST_DB_* environment variables.
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
    "port": int(os.getenv("TEST_DB_PORT") or os.getenv("DB_PORT", "3306")),
    "user": os.getenv("TEST_DB_USER") or os.getenv("DB_USER", "postgres"),
    "password": os.getenv("TEST_DB_PASSWORD") or os.getenv("DB_PASSWORD", "postgres"),
    "dbname": os.getenv("TEST_DB_NAME") or f"test_{os.getenv('DB_NAME', 'apus_mab')}",
}

_ENV_KEY_MAP = {"host": "DB_HOST", "port": "DB_PORT", "user": "DB_USER", "password": "DB_PASSWORD", "dbname": "DB_NAME"}
for key, val in TEST_DB_CONFIG.items():
    # Forzar (no setdefault): los tests NUNCA deben conectarse a la BD del .env.
    os.environ[_ENV_KEY_MAP[key]] = str(val)


def db_available() -> bool:
    """Check if the test database is reachable."""
    try:
        import mysql.connector
        conn = mysql.connector.connect(host=TEST_DB_CONFIG["host"], port=TEST_DB_CONFIG["port"], user=TEST_DB_CONFIG["user"], password=TEST_DB_CONFIG["password"], database=TEST_DB_CONFIG["dbname"], connect_timeout=3)
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
        pytest.skip("MySQL test database not available")
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
            "items_descripcion": "Excavacion manual",
            "item_unidad": "M3",
            "precio_unitario": 85000.00,
            "codigo_insumo": "EXC-001",
            "tipo_insumo": "Mano de obra",
            "insumo_descripcion": "Excavacion manual en terreno comun",
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

    # Limpieza previa: si una corrida anterior falló a mitad del setup, el
    # teardown nunca corrió y quedarían filas que rompen el índice único.
    execute_query("DELETE FROM apus", fetch=False)

    # Cada fila puede tener columnas distintas: el INSERT se arma por fila.
    for row in sample_rows:
        columns = list(row.keys())
        placeholders = ", ".join("%s" for _ in columns)
        col_names = ", ".join(columns)
        execute_query(
            f"INSERT INTO apus ({col_names}) VALUES ({placeholders})",
            tuple(row.values()),
            fetch=False,
        )

    yield

    execute_query("DELETE FROM apus", fetch=False)


@pytest.fixture
def auth_token(test_db):
    """Crea un usuario admin de prueba y devuelve un JWT válido."""
    from db_config import execute_query
    from src.presentation.auth import create_access_token, hash_password

    telefono = "test-admin-000"
    execute_query("DELETE FROM users WHERE phone = %s", (telefono,), fetch=False)
    execute_query(
        "INSERT INTO users (name, cc, email, password, phone, position, proyecto) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        ("Admin Test", telefono, "admin@test.local", hash_password("test-password"), telefono, "Admin Test", "LOCAL"),
        fetch=False,
    )
    rows = execute_query("SELECT id, phone AS telefono FROM users WHERE phone = %s", (telefono,))
    user = rows[0]
    rol_row = execute_query("SELECT id FROM rol WHERE codigo = 'admin'")
    if rol_row:
        execute_query(
            "INSERT IGNORE INTO usuario_rol (user_id, rol_id) VALUES (%s, %s)",
            (user["id"], rol_row[0]["id"]),
            fetch=False,
        )
    token = create_access_token({
        "sub": str(user["id"]),
        "telefono": user["telefono"],
        "rol": "admin",
        "nombre": "Admin Test",
    })
    yield token
    execute_query("DELETE FROM users WHERE phone = %s", (telefono,), fetch=False)


@pytest.fixture
def client(seed_data, auth_token):
    """FastAPI TestClient with seeded data and an authenticated admin session."""
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {auth_token}"})
        yield c
