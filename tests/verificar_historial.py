"""
Verificar que los datos se guardaron en la tabla historial_conversaciones
"""

from db_config import get_db_connection

def verificar_datos():
    """Verifica los datos en la tabla historial_conversaciones."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Contar total de registros
        cursor.execute("SELECT COUNT(*) as total FROM historial_conversaciones")
        total = cursor.fetchone()['total']
        print(f"\n📊 Total de conversaciones en la BD: {total}")
        
        # Obtener últimas 10 conversaciones
        cursor.execute("""
            SELECT telefono, mensaje_usuario, 
                   LEFT(sql_generado, 60) as sql_preview,
                   timestamp
            FROM historial_conversaciones
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        
        registros = cursor.fetchall()
        
        if registros:
            print(f"\n📋 Últimas {len(registros)} conversaciones:\n")
            print("-" * 80)
            for i, reg in enumerate(registros, 1):
                print(f"{i}. [{reg['timestamp']}]")
                print(f"   Tel: {reg['telefono']}")
                print(f"   Msg: {reg['mensaje_usuario']}")
                print(f"   SQL: {reg['sql_preview']}...")
                print()
        else:
            print("\n⚠️ No hay registros en la tabla")
        
        cursor.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    verificar_datos()
