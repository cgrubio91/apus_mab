"""
🗄️ Database Configuration Module
Centralizes database connection logic for PostgreSQL (Google Cloud SQL)
"""

import logging
import os

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

log = logging.getLogger("mapus.db")


class DatabaseConfig:
    """Database configuration singleton"""

    def __init__(self):
        self.host = os.getenv("DB_HOST")
        self.port = int(os.getenv("DB_PORT", 5432))
        self.name = os.getenv("DB_NAME")
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.sslmode = os.getenv("DB_SSLMODE", "prefer")
        self.cloud_sql_connection_name = os.getenv("CLOUD_SQL_CONNECTION_NAME")

    def validate(self):
        """Validate that all required configuration is present"""
        required = {
            "DB_HOST": self.host,
            "DB_NAME": self.name,
            "DB_USER": self.user,
            "DB_PASSWORD": self.password,
        }

        missing = [key for key, value in required.items() if not value]

        if missing:
            raise ValueError(
                f"Missing required database configuration: {', '.join(missing)}\n"
                "Check your .env file."
            )

    def get_connection_params(self):
        """Get connection parameters as a dictionary"""
        if self.cloud_sql_connection_name:
            return {
                "user": self.user,
                "password": self.password,
                "dbname": self.name,
                "host": f"/cloudsql/{self.cloud_sql_connection_name}",
            }
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.name,
            "user": self.user,
            "password": self.password,
            "sslmode": self.sslmode,
            "connect_timeout": 30,
        }


db_config = DatabaseConfig()


def get_db_connection():
    """Create and return a new database connection."""
    db_config.validate()
    params = db_config.get_connection_params()

    try:
        conn = psycopg2.connect(**params)
        return conn
    except psycopg2.Error as e:
        log.error("Database connection failed: %s", e)
        raise


def execute_query(query, params=None, fetch=True, dict_cursor=True):
    """
    Execute a SQL query with parameterized arguments (safe from injection).

    Args:
        query: SQL query with %s placeholders
        params: tuple of values for placeholders
        fetch: True for SELECT, False for INSERT/UPDATE/DELETE
        dict_cursor: True to return rows as dicts

    Returns:
        list of rows (fetch=True) or affected row count (fetch=False)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor if dict_cursor else None)

        cursor.execute(query, params)

        if fetch:
            results = cursor.fetchall()
            cursor.close()
            return results

        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        return affected

    except Exception as e:
        if conn:
            conn.rollback()
        log.error("Query execution failed: %s | Query: %s", e, query[:200])
        raise
    finally:
        if conn:
            conn.close()


def test_connection():
    """Test database connection, return status dict."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {"status": "success", "version": version}
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = test_connection()
    if result["status"] == "success":
        log.info("✅ Connection OK — %s", result["version"])
    else:
        log.error("❌ %s", result["message"])
