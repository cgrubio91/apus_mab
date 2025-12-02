import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

print("🔍 Probando conexión a TiDB...")
print(f"Host: {os.getenv('DB_HOST')}")
print(f"Port: {os.getenv('DB_PORT', 4000)}")
print(f"User: {os.getenv('DB_USER')}")
print(f"Database: {os.getenv('DB_NAME')}")

try:
    ssl_ca_path = os.getenv("DB_SSL_CA", "isrgrootx1.pem")
    
    config = {
        "host": os.getenv("DB_HOST"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
        "port": int(os.getenv("DB_PORT", 4000)),
    }
    
    if os.path.exists(ssl_ca_path):
        config["ssl_ca"] = ssl_ca_path
        config["ssl_verify_cert"] = True
        config["ssl_verify_identity"] = True
        print(f"🔒 Usando certificado SSL: {ssl_ca_path}")
    else:
        config["ssl_disabled"] = False
        print("⚠️ Certificado no encontrado, usando SSL sin verificación")

    
    print("\n📡 Intentando conectar...")
    conn = mysql.connector.connect(**config)
    print("✅ ¡Conexión exitosa a TiDB!")
    
    cursor = conn.cursor()
    cursor.execute("SELECT VERSION()")
    version = cursor.fetchone()
    print(f"📊 Versión de TiDB: {version[0]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error de conexión: {e}")
    print(f"\nTipo de error: {type(e).__name__}")
