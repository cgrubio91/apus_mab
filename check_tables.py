import psycopg2
import os

# --- 🛠️ CONFIGURACIÓN DE CONEXIÓN ---
# Nota: La librería psycopg2 usa 'dbname' en lugar de 'DB_NAME'
DB_HOST = "35.198.53.120"
DB_PORT = "5432"
DB_NAME = "apus-mab"
DB_USER = "postgres"
DB_PASSWORD = r"/9N+pL#kXFI|\v%z"
DB_SSLMODE = "require"
# db_sslmode=require implica usar SSL
# Para conexiones simples, a veces basta con solo el host, user, password, dbname y port.
# Si el requerimiento de Cloud SQL es estricto, es posible que necesites un certificado SSL.
# Para esta prueba inicial, usaremos los parámetros básicos.

def test_cloudsql_connection():
    """
    Intenta conectarse a la base de datos PostgreSQL en Google Cloud SQL.
    """
    conn = None
    try:
        print(f"🔗 Intentando conectar a PostgreSQL en {DB_HOST}:{DB_PORT}...")
        
        # Conexión básica usando psycopg2
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            sslmode=DB_SSLMODE
            # Si la conexión falla debido a SSL, podrías intentar añadir:
            # sslmode="require" 
            # *PERO* asegúrate de que tu entorno local tiene los certificados raíz de Cloud SQL.
        )
        
        # Si la conexión es exitosa
        print("✅ ¡Conexión a Cloud SQL exitosa!")
        
        # Opcional: Ejecutar una consulta simple para verificar que la DB está viva
        with conn.cursor() as cursor:
            cursor.execute("SELECT version();")
            db_version = cursor.fetchone()
            print(f"📊 Versión de la base de datos: {db_version[0]}")
            
        return True

    except psycopg2.OperationalError as e:
        print(f"❌ FALLÓ LA CONEXIÓN (Error Operacional):")
        print(f"   Asegúrate que la IP de tu red local está autorizada en Google Cloud SQL.")
        print(f"   Error: {e}")
        return False
    
    except Exception as e:
        print(f"❌ Ocurrió un error inesperado durante la conexión: {e}")
        return False
        
    finally:
        if conn:
            conn.close()
            print("📴 Conexión cerrada.")

if __name__ == "__main__":
    test_cloudsql_connection()