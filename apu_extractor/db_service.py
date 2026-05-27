"""
🗃️ DB Service Module
Provides ultra-resilient, memory-safe, and high-performance bulk insertion operations
for parsed APU datasets. Leverages psycopg2 execute_values for real batch speed.
"""

import logging
import unicodedata
from decimal import Decimal
from typing import List, Dict, Any, Generator, Tuple, TypedDict
from psycopg2 import DatabaseError
from psycopg2.extras import execute_values
from db_config import get_db_connection

log = logging.getLogger("mapus.extractor.db")

# ── Configuración de Infraestructura Regulable ───────────────────────
MAX_ERRORS_RETAINED = 100
BULK_PAGE_SIZE = 500       # Configurable según RAM/CPU del servidor (local vs cloud)
STREAM_BATCH_SIZE = 200    # Chunks optimizados para aprovechar execute_values por red

# ==========================================================
# TYPEDDICTS FOR TYPING CONSISTENCY
# ==========================================================

class StreamProgress(TypedDict):
    type: str
    inserted: int
    total: int
    errors: List[str]
    errors_truncated: bool


# ==========================================================
# SANITIZATION HELPERS
# ==========================================================

def _std_field(item: Dict[str, Any], field_name: str, is_numeric: bool = False) -> Any:
    """
    Normaliza unicode (NFKC), limpia espacios en blanco y transforma guiones 
    huérfanos de PDFs en tipos None o Decimals financieros limpios.
    """
    val = item.get(field_name)
    
    if val in ("–", "—", "-", "", None):
        return None
        
    if isinstance(val, str):
        val = unicodedata.normalize("NFKC", val).strip()
        if val in ("–", "—", "-", ""):
            return None

    if is_numeric and val is not None:
        try:
            return Decimal(str(val))
        except (ValueError, TypeError):
            return None
            
    return val


# ==========================================================
# CORE DATABASE OPERATIONS
# ==========================================================

def insert_apus_batch(apus_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Inserts a list of APU dicts using high-performance execute_values (Real bulk insert).
    Falls back to a Savepoint-nested row-by-row session if the batch fails.
    
    Returns metrics tracking successful insertions, skipped duplicates, and structural errors.
    """
    if not apus_list:
        return {"status": "success", "count": 0, "duplicates": 0, "errors": []}
        
    sql = """
        INSERT INTO apus (
            fecha_aprobacion_apu, fecha_analisis_apu,
            ciudad, pais, entidad, contratista, nombre_proyecto,
            numero_contrato, item, items_descripcion, item_unidad,
            precio_unitario, precio_unitario_sin_aiu,
            codigo_insumo, tipo_insumo, insumo_descripcion,
            insumo_unidad, rendimiento_insumo,
            precio_unitario_apu, precio_parcial_apu,
            observacion, link_documento
        )
        VALUES %s
        ON CONFLICT (numero_contrato, item, codigo_insumo, link_documento) DO NOTHING
        RETURNING 1;
    """
    
    tuple_data: List[Tuple[Any, ...]] = []
    for item in apus_list:
        row = (
            _std_field(item, "fecha_aprobacion_apu"),
            _std_field(item, "fecha_analisis_apu"),
            _std_field(item, "ciudad"),
            _std_field(item, "pais"),
            _std_field(item, "entidad"),
            _std_field(item, "contratista"),
            _std_field(item, "nombre_proyecto"),
            _std_field(item, "numero_contrato"),
            _std_field(item, "item"),
            _std_field(item, "items_descripcion"),
            _std_field(item, "item_unidad"),
            _std_field(item, "precio_unitario", is_numeric=True),
            _std_field(item, "precio_unitario_sin_aiu", is_numeric=True),
            _std_field(item, "codigo_insumo"),
            _std_field(item, "tipo_insumo"),
            _std_field(item, "insumo_descripcion"),
            _std_field(item, "insumo_unidad"),
            _std_field(item, "rendimiento_insumo", is_numeric=True),
            _std_field(item, "precio_unitario_apu", is_numeric=True),
            _std_field(item, "precio_parcial_apu", is_numeric=True),
            _std_field(item, "observacion"),
            _std_field(item, "link_documento")
        )
        tuple_data.append(row)
        
    total_requested = len(tuple_data)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                execute_values(cursor, sql, tuple_data, page_size=BULK_PAGE_SIZE)
                # En el bulk principal por bloques controlados (max 500), fetchall es seguro y preciso
                inserted_count = len(cursor.fetchall())
                
                # CORRECCIÓN: Cálculo exacto de duplicados para telemetría limpia en dashboards
                duplicates_count = total_requested - inserted_count
                
                return {
                    "status": "success", 
                    "count": inserted_count, 
                    "duplicates": duplicates_count,
                    "errors": []
                }
                
    except DatabaseError as e:
        error_msg = f"Database bulk execution failed: {e}"
        log.warning("⚠️ %s. Retrying via safe Savepoint nested transaction fallback.", error_msg)
        
        inserted_count = 0
        db_errors = [error_msg]
        
        # En el fallback row-by-row no requerimos RETURNING 1 porque rowcount es directo y seguro
        single_sql = """
            INSERT INTO apus (
                fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad, contratista, 
                nombre_proyecto, numero_contrato, item, items_descripcion, item_unidad, 
                precio_unitario, precio_unitario_sin_aiu, codigo_insumo, tipo_insumo, 
                insumo_descripcion, insumo_unidad, rendimiento_insumo, precio_unitario_apu, 
                precio_parcial_apu, observacion, link_documento
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (numero_contrato, item, codigo_insumo, link_documento) DO NOTHING;
        """
        
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    for i, row in enumerate(tuple_data):
                        try:
                            # CORRECCIÓN: Estilo limpio sin puntos y comas innecesarios
                            cursor.execute("SAVEPOINT apu_insert_sp")
                            cursor.execute(single_sql, row)
                            
                            # OPTIMIZACIÓN DE MEMORIA: rowcount evita instanciar arrays pesados en RAM
                            inserted_count += cursor.rowcount
                            
                        except DatabaseError as re:
                            cursor.execute("ROLLBACK TO SAVEPOINT apu_insert_sp")
                            if len(db_errors) < MAX_ERRORS_RETAINED:
                                db_errors.append(f"Row {i} (Project: {row[6]}, Item: {row[8]}): {re}")
                    
                    conn.commit()
        except Exception as conn_err:
            log.exception("Critical infrastructure loss during savepoint processing")
            db_errors.append(f"Failed to execute savepoint fallback: {conn_err}")
            
        # Cálculo de duplicados en el bloque de contingencia
        # Restamos los errores reales detectados del delta para no inflar la métrica de duplicidad
        real_errors_count = max(0, len(db_errors) - 1)  # Descontamos el error base de la cabecera
        duplicates_count = max(0, total_requested - inserted_count - real_errors_count)

        # CORRECCIÓN: Telemetría semántica fina. El estado solo es 'failed' si no se inyectó un solo dato.
        if inserted_count + duplicates_count == total_requested and real_errors_count == 0:
            current_status = "success"
        elif inserted_count > 0 or duplicates_count > 0:
            current_status = "partial"
        else:
            current_status = "failed"

        return {
            "status": current_status,
            "count": inserted_count,
            "duplicates": duplicates_count,
            "errors": db_errors
        }


def insert_apus_stream(
    apus_list: List[Dict[str, Any]], 
    batch_size: int = STREAM_BATCH_SIZE
) -> Generator[StreamProgress, None, None]:
    """
    Generator that processes bulk data streams using transactional chunks. 
    Yields highly predictive TypedDict statuses protected against RAM blowups.
    """
    total = len(apus_list)
    if not total:
        yield {"type": "complete", "inserted": 0, "total": 0, "errors": [], "errors_truncated": False}
        return

    inserted = 0
    all_errors: List[str] = []
    errors_truncated = False

    for start in range(0, total, batch_size):
        batch = apus_list[start : start + batch_size]
        try:
            result = insert_apus_batch(batch)
            inserted += result.get("count", 0)
            
            if result.get("errors"):
                if len(all_errors) < MAX_ERRORS_RETAINED:
                    all_errors.extend(result["errors"])
                else:
                    errors_truncated = True
        except Exception:
            log.exception("Stream execution batch failure")
            if len(all_errors) < MAX_ERRORS_RETAINED:
                all_errors.append("Excepción crítica en el bloque de transmisión de streaming.")
            else:
                errors_truncated = True

        yield {
            "type": "progress",
            "inserted": min(inserted, total),
            "total": total,
            "errors": all_errors[:MAX_ERRORS_RETAINED],
            "errors_truncated": errors_truncated
        }

    yield {
        "type": "complete",
        "inserted": inserted,
        "total": total,
        "errors": all_errors[:MAX_ERRORS_RETAINED],
        "errors_truncated": errors_truncated
    }