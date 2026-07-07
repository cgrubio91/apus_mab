"""
Script de prueba para el sistema de memoria conversacional
"""

from db_config import get_db_connection

def guardar_conversacion(telefono: str, mensaje_usuario: str, sql_generado: str, respuesta_bot: str):
    """Guarda una interacción en el historial de conversaciones."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO historial_conversaciones (telefono, mensaje_usuario, sql_generado, respuesta_bot)
            VALUES (%s, %s, %s, %s)
        """, (telefono, mensaje_usuario, sql_generado, respuesta_bot))
        conn.commit()
        cursor.close()
        print(f"✅ Conversación guardada para {telefono}")
    except Exception as e:
        print(f"❌ Error guardando conversación: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def obtener_historial(telefono: str, limite: int = 5):
    """Recupera las últimas conversaciones del usuario."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT mensaje_usuario, sql_generado, respuesta_bot, timestamp
            FROM historial_conversaciones
            WHERE telefono = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (telefono, limite))
        historial = cursor.fetchall()
        cursor.close()
        return list(reversed(historial))
    except Exception as e:
        print(f"❌ Error recuperando historial: {e}")
        return []
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    # Número de prueba
    telefono_test = "whatsapp:+573001234567"
    
    print("\n🧪 PRUEBA 1: Guardar conversaciones de ejemplo")
    print("=" * 50)
    
    # Simular 3 conversaciones
    conversaciones = [
        {
            "mensaje": "Dame los ítems más caros de Bogotá",
            "sql": "SELECT items_descripcion, precio_unitario FROM apus WHERE ciudad='Bogotá' ORDER BY precio_unitario DESC LIMIT 5",
            "respuesta": "Hola! Aquí están los 5 ítems más caros..."
        },
        {
            "mensaje": "Y de Medellín?",
            "sql": "SELECT items_descripcion, precio_unitario FROM apus WHERE ciudad='Medellín' ORDER BY precio_unitario DESC LIMIT 5",
            "respuesta": "Claro! Los ítems más caros de Medellín son..."
        },
        {
            "mensaje": "Compara los precios de excavación",
            "sql": "SELECT ciudad, AVG(precio_unitario) FROM apus WHERE items_descripcion LIKE '%excavación%' GROUP BY ciudad",
            "respuesta": "Aquí está la comparación de precios de excavación..."
        }
    ]
    
    for conv in conversaciones:
        guardar_conversacion(
            telefono_test,
            conv["mensaje"],
            conv["sql"],
            conv["respuesta"]
        )
    
    print("\n🧪 PRUEBA 2: Recuperar historial")
    print("=" * 50)
    
    historial = obtener_historial(telefono_test, limite=5)
    
    if historial:
        print(f"\n📚 Se encontraron {len(historial)} conversaciones:\n")
        for i, conv in enumerate(historial, 1):
            print(f"--- Conversación {i} ---")
            print(f"Usuario: {conv['mensaje_usuario']}")
            print(f"SQL: {conv['sql_generado'][:80]}...")
            print(f"Timestamp: {conv['timestamp']}")
            print()
    else:
        print("❌ No se encontró historial")
    
    print("\n🧪 PRUEBA 3: Simular contexto para nueva pregunta")
    print("=" * 50)
    
    nueva_pregunta = "Ahora muéstrame solo de Cali"
    
    if historial:
        contexto = "\n\nCONTEXTO DE CONVERSACIONES PREVIAS:\n"
        for conv in historial:
            contexto += f"Usuario: {conv['mensaje_usuario']}\n"
            if conv['sql_generado']:
                contexto += f"SQL: {conv['sql_generado'][:100]}...\n"
        
        print(f"Nueva pregunta: '{nueva_pregunta}'")
        print("\nContexto que se enviaría a Gemini:")
        print(contexto)
        print("\nCon este contexto, Gemini entendería que 'Ahora muéstrame solo de Cali'")
        print("se refiere a lo mismo que la consulta anterior pero filtrando por Cali.")
    
    print("\n✅ Todas las pruebas completadas!")
