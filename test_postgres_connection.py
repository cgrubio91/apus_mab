"""
🔍 PostgreSQL Connection Test Script
Tests the database connection using centralized configuration
"""

from db_config import test_connection, db_config

def main():
    print("🔌 Intentando conectar a PostgreSQL...")
    print(f"   Host: {db_config.host}:{db_config.port}")
    print(f"   User: {db_config.user}")
    print(f"   DB:   {db_config.name}")
    print(f"   SSL:  {db_config.sslmode}")
    
    result = test_connection()
    
    if result["status"] == "success":
        print("\n✅ ¡CONEXIÓN EXITOSA!")
        print(f"📊 Versión del servidor: {result['version']}")
    else:
        print("\n❌ ERROR DE CONEXIÓN:")
        print(f"   {result['message']}")
        print("\n💡 SUGERENCIA: Verifica que tu IP actual esté en 'Authorized Networks' de Cloud SQL.")
        print("   O usa el Cloud SQL Auth Proxy si la IP cambia o hay firewall.")

if __name__ == "__main__":
    main()
