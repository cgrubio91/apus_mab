"""
🗄️ Database Configuration Module
Centralizes database connection logic for PostgreSQL (Google Cloud SQL)
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


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
            "DB_PASSWORD": self.password
        }
        
        missing = [key for key, value in required.items() if not value]
        
        if missing:
            raise ValueError(
                f"Missing required database configuration: {', '.join(missing)}\n"
                f"Please check your .env file."
            )
    
    def get_connection_params(self):
        """Get connection parameters as a dictionary"""
        if self.cloud_sql_connection_name:
            # Use Unix socket for Cloud SQL Auth Proxy
            return {
                "user": self.user,
                "password": self.password,
                "dbname": self.name,
                "host": f"/cloudsql/{self.cloud_sql_connection_name}"
            }
        else:
            # Use TCP/IP connection
            return {
                "host": self.host,
                "port": self.port,
                "dbname": self.name,
                "user": self.user,
                "password": self.password,
                "sslmode": self.sslmode,
                "connect_timeout": 30
            }


# Global configuration instance
db_config = DatabaseConfig()


def get_db_connection():
    """
    Create and return a new database connection.
    
    Returns:
        psycopg2.connection: Active database connection
        
    Raises:
        ValueError: If database configuration is invalid
        psycopg2.Error: If connection fails
    """
    db_config.validate()
    params = db_config.get_connection_params()
    
    try:
        conn = psycopg2.connect(**params)
        return conn
    except psycopg2.Error as e:
        raise Exception(f"Failed to connect to database: {e}")


def execute_query(query, params=None, fetch=True, dict_cursor=True):
    """
    Execute a SQL query and return results.
    
    Args:
        query (str): SQL query to execute
        params (tuple, optional): Query parameters for safe substitution
        fetch (bool): Whether to fetch results (for SELECT queries)
        dict_cursor (bool): Whether to use RealDictCursor for dict-like results
        
    Returns:
        list: Query results (if fetch=True)
        int: Number of affected rows (if fetch=False)
        
    Raises:
        Exception: If query execution fails
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor_factory = RealDictCursor if dict_cursor else None
        cursor = conn.cursor(cursor_factory=cursor_factory)
        
        cursor.execute(query, params)
        
        if fetch:
            results = cursor.fetchall()
            cursor.close()
            return results
        else:
            conn.commit()
            affected_rows = cursor.rowcount
            cursor.close()
            return affected_rows
            
    except Exception as e:
        if conn:
            conn.rollback()
        raise Exception(f"Query execution failed: {e}")
    finally:
        if conn:
            conn.close()


def test_connection():
    """
    Test database connection.
    
    Returns:
        dict: Connection status and database version
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        return {
            "status": "success",
            "message": "Database connection successful",
            "version": version
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


if __name__ == "__main__":
    # Test the connection when run directly
    print("🔌 Testing database connection...")
    result = test_connection()
    
    if result["status"] == "success":
        print(f"✅ {result['message']}")
        print(f"📊 {result['version']}")
    else:
        print(f"❌ Connection failed: {result['message']}")
