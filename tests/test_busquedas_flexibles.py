"""
Script de prueba para verificar búsquedas flexibles con ILIKE
Prueba que el sistema entiende consultas en lenguaje natural
"""

import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

def gemini_generate(prompt: str) -> str:
    """Llama a la API de Gemini para generar texto."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=30)
        data = r.json()
        if "candidates" not in data:
            return f"Error: {json.dumps(data, indent=2)}"
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        return f"Error: {e}"


def test_prompt_sql(mensaje_usuario: str) -> str:
    """Prueba el prompt SQL mejorado con un mensaje del usuario."""
    
    prompt_sql = f"""
    Actúa como un asistente experto en bases de datos PostgreSQL y en análisis de precios unitarios (APU) de obras civiles.
    Convierte la solicitud del usuario en una consulta SQL válida, considerando que el usuario NO conoce los nombres técnicos de las columnas.

    Tabla: apus
    Columnas disponibles:
    - fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad, contratista,
      nombre_proyecto, numero_contrato, item, items_descripcion, item_unidad,
      precio_unitario, precio_unitario_sin_aiu, codigo_insumo, tipo_insumo,
      insumo_descripcion, insumo_unidad, rendimiento_insumo, precio_unitario_apu,
      precio_parcial_apu, observacion, link_documento

    REGLAS CRÍTICAS PARA BÚSQUEDAS:
    
    1. **BÚSQUEDAS FLEXIBLES** - Siempre usa ILIKE (case-insensitive) con % para búsquedas parciales:
       - Usuario dice "proyecto X" → WHERE nombre_proyecto ILIKE '%X%'
       - Usuario dice "item de concreto" → WHERE items_descripcion ILIKE '%concreto%'
       - Usuario dice "insumo cemento" → WHERE insumo_descripcion ILIKE '%cemento%'
       - Usuario dice "ciudad Bogotá" → WHERE ciudad ILIKE '%bogotá%'
    
    2. **MAPEO DE LENGUAJE NATURAL A COLUMNAS**:
       - "proyecto" / "obra" → nombre_proyecto
       - "item" / "actividad" → items_descripcion
       - "insumo" / "material" → insumo_descripcion
       - "precio" / "valor" / "costo" → precio_unitario
       - "ciudad" / "lugar" → ciudad
       - "contratista" / "empresa" → contratista
       - "más caro" / "más costoso" → ORDER BY precio_unitario DESC
       - "más barato" / "más económico" → ORDER BY precio_unitario ASC
       - "cuántos" / "cantidad" → COUNT(*)
       - "promedio" → AVG(precio_unitario)
       - "total" → SUM(precio_unitario)
    
    3. **EJEMPLOS DE CONSULTAS COMUNES**:
       
       ❌ INCORRECTO:
       Usuario: "cuántos items tiene el proyecto la macarena"
       SQL MAL: SELECT * FROM apus WHERE nombre_proyecto = 'la macarena'
       
       ✅ CORRECTO:
       Usuario: "cuántos items tiene el proyecto la macarena"
       SQL: SELECT COUNT(DISTINCT items_descripcion) as total_items FROM apus WHERE nombre_proyecto ILIKE '%macarena%'
       
       ✅ CORRECTO:
       Usuario: "cuál es el item más costoso de la macarena"
       SQL: SELECT items_descripcion, precio_unitario FROM apus WHERE nombre_proyecto ILIKE '%macarena%' ORDER BY precio_unitario DESC LIMIT 1
       
       ✅ CORRECTO:
       Usuario: "dame los items de excavación"
       SQL: SELECT items_descripcion, precio_unitario FROM apus WHERE items_descripcion ILIKE '%excavación%' ORDER BY precio_unitario DESC LIMIT 20
       
       ✅ CORRECTO:
       Usuario: "proyectos en Bogotá"
       SQL: SELECT DISTINCT nombre_proyecto, ciudad FROM apus WHERE ciudad ILIKE '%bogotá%' LIMIT 20
    
    4. **OTRAS REGLAS**:
       - Limita resultados a 20 con LIMIT 20 (a menos que el usuario especifique otra cantidad)
       - Ordena de manera lógica (por precio, fecha, nombre, etc.)
       - Usa DISTINCT cuando sea necesario para evitar duplicados
       - Si pide conteo, usa COUNT(*)
       - Si pide promedio, usa AVG()
       - Para comparaciones, usa GROUP BY con la columna apropiada
       - Si el usuario hace referencia a consultas anteriores, usa el contexto previo
    
    5. **NUNCA USES**:
       - Igualdad exacta con = para textos (⚠️ casi siempre usar ILIKE)
       - Formato Markdown ni ```sql```
       - Consultas que no sean SELECT
    
    Usuario pregunta: "{mensaje_usuario}"
    
    Genera SOLO la consulta SQL, sin explicaciones.
    """
    
    return gemini_generate(prompt_sql)


if __name__ == "__main__":
    print("\n" + "="*80)
    print("🧪 PRUEBAS DE BÚSQUEDAS FLEXIBLES CON ILIKE")
    print("="*80)
    
    # Casos de prueba basados en la imagen del usuario
    casos_prueba = [
        "cuantos item tiene el proyecto la macarena",
        "cual es el item mas costoso de la macarena?",
        "dame los items de excavación",
        "proyectos en Bogotá",
        "precio promedio de concreto",
        "items más caros",
        "cuántos proyectos hay en total",
        "dame los insumos de cemento",
        "compara precios de Bogotá vs Medellín",
    ]
    
    for i, caso in enumerate(casos_prueba, 1):
        print(f"\n{'─'*80}")
        print(f"📝 CASO {i}: {caso}")
        print(f"{'─'*80}")
        
        sql_generado = test_prompt_sql(caso)
        
        # Limpiar el SQL de posibles marcadores markdown
        import re
        sql_generado = re.sub(r"```sql|```", "", sql_generado).strip()
        
        print(f"\n🔍 SQL Generado:")
        print(f"   {sql_generado}")
        
        # Verificar que use ILIKE en casos donde debe usarlo
        if "proyecto" in caso.lower() or "item" in caso.lower() or "insumo" in caso.lower():
            if "ILIKE" in sql_generado.upper():
                print(f"   ✅ Usa ILIKE correctamente")
            else:
                print(f"   ⚠️ ADVERTENCIA: No usa ILIKE (puede no encontrar resultados)")
        
        # Verificar que use COUNT cuando pide cantidad
        if "cuántos" in caso.lower() or "cantidad" in caso.lower():
            if "COUNT" in sql_generado.upper():
                print(f"   ✅ Usa COUNT correctamente")
            else:
                print(f"   ⚠️ ADVERTENCIA: No usa COUNT para contar")
        
        # Verificar que ordene cuando pide "más caro" o "más costoso"
        if "más caro" in caso.lower() or "más costoso" in caso.lower():
            if "ORDER BY" in sql_generado.upper() and "DESC" in sql_generado.upper():
                print(f"   ✅ Ordena correctamente (DESC)")
            else:
                print(f"   ⚠️ ADVERTENCIA: No ordena por precio descendente")
    
    print("\n" + "="*80)
    print("✅ PRUEBAS COMPLETADAS")
    print("="*80)
    print("\n💡 Revisar que las consultas usen ILIKE para búsquedas de texto parciales")
    print("💡 Esto evitará el problema de 'No se encontraron resultados'\n")
