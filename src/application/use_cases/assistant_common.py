"""
Application: helpers compartidos entre los asistentes NL→SQL (chat web y WhatsApp).
Centraliza normalización de SQL, ejecución segura, historial y persistencia
de conversaciones para evitar lógica duplicada.
"""

import logging
import re

from src.infrastructure.ai.provider import ai_provider
from src.infrastructure.database.connection import execute_query, get_db_connection

log = logging.getLogger("mapus.application.assistant")


def normalize_sql_for_mysql(sql: str) -> str:
    """Convert common PostgreSQL syntax to MySQL-compatible."""
    # ILIKE → LIKE (MySQL LIKE is case-insensitive with utf8 collation)
    sql = re.sub(r'\bILIKE\b', 'LIKE', sql, flags=re.IGNORECASE)
    # DISTINCT ON (x, y) → DISTINCT (strip the ON clause)
    sql = re.sub(r'\bDISTINCT\s+ON\s*\([^)]*\)', 'DISTINCT', sql, flags=re.IGNORECASE)
    # :: type cast → nothing (MySQL doesn't support it)
    sql = re.sub(r'::\w+', '', sql)
    # TRUE/FALSE boolean → 1/0
    sql = re.sub(r'\bTRUE\b', '1', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bFALSE\b', '0', sql, flags=re.IGNORECASE)
    return sql


def gemini_generate(prompt: str, system: str, timeout: int = 300) -> str:
    return ai_provider.generate_text(prompt, system=system, timeout=timeout)


def strip_sql_markdown(raw_sql: str) -> str:
    return re.sub(r"```sql|```", "", raw_sql).strip()


def ejecutar_sql(query: str) -> list[dict]:
    """Ejecuta un SELECT ya validado. Nunca filtra el error real al cliente."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(query)
                return cursor.fetchall()
    except Exception as e:
        log.error("SQL execution error [%s]: %s", type(e).__name__, e)
        log.error("Failed SQL: %s", query[:500])
        return [{"error": f"Error interno en la ejecución de la consulta SQL: {type(e).__name__}"}]


def obtener_historial(telefono: str, limite: int = 5) -> list[dict]:
    try:
        rows = execute_query(
            """SELECT mensaje_usuario, sql_generado, respuesta_bot, timestamp
               FROM historial_conversaciones
               WHERE telefono = %s ORDER BY timestamp DESC LIMIT %s""",
            (telefono, limite),
        )
        return list(reversed(rows)) if rows else []
    except Exception:
        log.exception("Error retrieving history for %s", telefono)
        return []


def guardar_conversacion(telefono: str, mensaje: str, sql_: str, respuesta: str):
    try:
        execute_query(
            """INSERT INTO historial_conversaciones (telefono, mensaje_usuario, sql_generado, respuesta_bot)
               VALUES (%s, %s, %s, %s)""",
            (telefono, mensaje, sql_, respuesta),
            fetch=False,
        )
    except Exception:
        log.exception("Failed to store conversation for %s", telefono)


def build_schema_prompt() -> str:
    """Genera la descripción de tablas y reglas para el prompt NL→SQL."""
    return """TABLAS DISPONIBLES EN LA BASE DE DATOS (MySQL 8.0):

1. apus: Banco interno de APUs aprobados de la organización.
   Cada fila representa un insumo individual dentro de un ítem APU.
   Columnas clave:
   - item: Código del ítem APU (ej: 'APU-001')
   - items_descripcion: Descripción del ítem APU
   - item_unidad: Unidad de medida del ítem (m3, m2, kg, ml, etc.)
   - precio_unitario: PRECIO UNITARIO TOTAL DEL ÍTEM APU (es constante para todas las filas del mismo ítem).
   - precio_unitario_apu: Precio unitario del INSUMO específico de esa fila (varía por insumo).
   - precio_parcial_apu: Rendimiento × precio_unitario_apu del insumo.
   - precio_unitario_sin_aiu: Precio del ítem sin AIU.
   - rendimiento_insumo: Rendimiento o consumo unitario del insumo.
   - codigo_insumo: Código del insumo.
   - insumo_descripcion: Nombre/descripción del insumo (cemento, arena, oficial, etc.).
   - tipo_insumo: Categoría ('Materiales', 'Mano de obra', 'Equipos', 'Transporte').
   - insumo_unidad: Unidad del insumo (kg, bulto, hr, etc.).
   - fecha_aprobacion_apu, fecha_analisis_apu: Fechas de aprobación/análisis.
   - ciudad, pais, entidad, contratista, nombre_proyecto, numero_contrato: Datos del proyecto.
   - proyecto_id: ID del proyecto asociado en la tabla de proyectos.

2. precio_referencia_externa: Precios de mercado y referencias externas (SECOP II, CYPE Colombia, Constructor Homecenter, ANI, IDU, INVÍAS).
   Úsala para comparar precios del banco interno contra el mercado exterior o consultar referencias públicas.
   Columnas clave:
   - fuente: Origen del dato ('SECOP II', 'CYPE Colombia', 'Constructor Homecenter', 'ANI', 'IDU', 'INVÍAS').
   - fuente_id: Identificador en la fuente externa (ej: código CYPE, id contrato).
   - granularidad: 'insumo' (insumo de obra), 'material' (producto de ferretería/retail), o 'contrato' (proyecto/contrato global).
   - descripcion: Nombre del insumo, material o contrato.
   - unidad: Unidad de medida.
   - codigo: Código de clasificación (si existe).
   - precio: Valor o precio unitario de referencia en COP.
   - rendimiento: Rendimiento unitario si es un insumo CYPE.
   - ciudad, departamento: Ubicación geográfica.
   - entidad: Entidad pública o contratante (ej. ANI, IDU, Invías).
   - proveedor: Empresa contratista o fabricante/marca.
   - fecha: Fecha del contrato o referencia.

3. indice_costos: Índices de costos DANE (series como 'ICCP' - Índice de Costos de la Construcción Pesada, o IPC).
   Úsala para indexar o ajustar precios históricos a valor presente.
   Columnas clave:
   - serie: Nombre de la serie (ej: 'ICCP').
   - periodo: Periodo mensual formato 'YYYY-MM' (ej: '2025-06').
   - valor: Valor del índice numérico.
   - fuente: Fuente del índice (ej: 'DANE').

4. insumo_maestro: Catálogo maestro canónico de insumos homologados.
   Columnas clave:
   - id: Identificador único del insumo.
   - descripcion_canonica: Nombre estandarizado del insumo.
   - unidad: Unidad estándar.
   - tipo_insumo: Tipo de insumo.
   - codigo: Código estándar.

5. precio_insumo_historico: Evolución histórica de precios por insumo maestro.
   Columnas clave:
   - insumo_maestro_id: FK hacia insumo_maestro(id).
   - precio: Precio registrado en esa fecha/fuente.
   - unidad: Unidad.
   - ciudad, departamento: Ubicación.
   - fecha: Fecha del registro de precio.
   - fuente: Fuente que aportó el precio.

REGLAS ABSOLUTAS (SINTAXIS ESTRICTAMENTE MySQL 8.0):
1. SOLO consultas SELECT o WITH.
2. SOLO las 5 tablas autorizadas arriba (apus, precio_referencia_externa, indice_costos, insumo_maestro, precio_insumo_historico).
3. Para búsquedas de texto usar siempre LIKE con % (NUNCA ILIKE — MySQL no soporta ILIKE).
4. Máximo LIMIT 20.
5. Nunca uses markdown en la respuesta SQL (sin comillas invertidas ni explicaciones).
6. Si no se puede responder con SELECT sobre las tablas permitidas, responde únicamente: INVALID_QUERY.
7. Nunca uses SELECT * sobre tablas reales; selecciona columnas explícitas.
8. Si el usuario pide comparar precios internos vs externos, puedes consultar o hacer UNION / JOIN entre apus y precio_referencia_externa según la consulta.
9. En apus, para listar ítems únicos usa SELECT DISTINCT item, items_descripcion, precio_unitario, nombre_proyecto, ciudad.
10. En apus, precio_unitario es el precio total del ítem APU; precio_unitario_apu es el precio unitario del insumo individual."""

