import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

print("🔍 Verificando tablas en TiDB...\n")

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
    
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    
    # Listar todas las tablas
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    
    print("📊 Tablas encontradas:")
    for table in tables:
        print(f"  - {table[0]}")
    
    print("\n" + "="*50)
    
    # Verificar tabla usuarios
    if ('usuarios',) in tables:
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        count = cursor.fetchone()[0]
        print(f"✅ Tabla 'usuarios': {count} registros")
        
        cursor.execute("SELECT telefono, nombre, rol, activo FROM usuarios")
        users = cursor.fetchall()
        print("\n👥 Usuarios registrados:")
        for user in users:
            status = "✅ Activo" if user[3] == 1 else "❌ Inactivo"
            print(f"  - {user[1]} ({user[0]}) - Rol: {user[2]} - {status}")
    else:
        print("❌ Tabla 'usuarios' no encontrada")
    
    print("\n" + "="*50)
    
    # Verificar tabla apus
    if ('apus',) in tables:
        cursor.execute("SELECT COUNT(*) FROM apus")
        count = cursor.fetchone()[0]
        print(f"✅ Tabla 'apus': {count} registros")
        
        if count > 0:
            cursor.execute("SELECT * FROM apus LIMIT 1")
            sample = cursor.fetchone()
            print(f"\n📝 Ejemplo de registro (primeras columnas):")
            cursor.execute("SHOW COLUMNS FROM apus")
            columns = cursor.fetchall()
            print(f"  Total de columnas: {len(columns)}")
            for i, col in enumerate(columns[:5]):  # Mostrar primeras 5 columnas
                print(f"  - {col[0]}: {col[1]}")
    else:
        print("❌ Tabla 'apus' no encontrada")
        print("\n⚠️  IMPORTANTE: Necesitas crear la tabla 'apus' para que el bot funcione.")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
