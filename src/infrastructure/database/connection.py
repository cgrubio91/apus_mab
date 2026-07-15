"""
Infrastructure: Database Connection Pool
Centralizes MySQL connection logic with production-grade pooling.
"""

import json
import logging
from datetime import datetime, date
from decimal import Decimal

import mysql.connector
from mysql.connector import pooling as mysql_pool

from src.config.settings import settings

log = logging.getLogger("mapus.db")


class DatabaseConfig:
    def __init__(self):
        self.host = settings.DB_HOST
        self.port = settings.DB_PORT
        self.name = settings.DB_NAME
        self.user = settings.DB_USER
        self.password = settings.DB_PASSWORD
        self.pool_min = settings.DB_POOL_MIN
        self.pool_max = settings.DB_POOL_MAX

    def validate(self):
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
        params = {
            "host": self.host,
            "port": self.port,
            "database": self.name,
            "user": self.user,
            "password": self.password,
            "connect_timeout": 30,
        }
        if settings.DB_SSLMODE and settings.DB_SSLMODE.lower() in ("require", "verify-ca", "verify-full"):
            params["ssl_ca"] = "ca.pem"
        return params


db_config = DatabaseConfig()


class DBEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.strftime("%Y-%m-%d")
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


_connection_pool = None


def _get_pool():
    global _connection_pool
    if _connection_pool is None:
        db_config.validate()
        params = db_config.get_connection_params()
        try:
            _connection_pool = mysql_pool.MySQLConnectionPool(
                pool_name="mapus_pool",
                pool_size=db_config.pool_max,
                pool_reset_session=True,
                **params,
            )
            log.info(
                "Connection pool created (size=%d)",
                db_config.pool_max,
            )
        except Exception as e:
            log.error("Failed to create connection pool: %s", e)
            raise
    return _connection_pool


class PoolConnection:
    def __init__(self, conn):
        self.conn = conn

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        put_connection(self.conn)
        return False

    def close(self):
        put_connection(self.conn)


def get_db_connection():
    global _connection_pool
    if _connection_pool is None:
        _get_pool()
    try:
        return PoolConnection(_get_pool().get_connection())
    except Exception as e:
        log.error("Failed to get connection from pool: %s", e)
        raise


def put_connection(conn):
    global _connection_pool
    if _connection_pool is not None and conn:
        try:
            conn.close()
            return
        except Exception:
            pass


def execute_query(query, params=None, fetch=True, dict_cursor=True):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=dict_cursor)
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
        put_connection(conn)


def test_connection():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        cursor.close()
        put_connection(conn)
        return {"status": "success", "version": version}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def close_pool():
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool = None
        log.info("Connection pool closed")
