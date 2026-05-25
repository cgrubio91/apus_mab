"""
🗃️ DB Service Module
Provides structured database query and insertion operations for the APU module.
Inherits connection pooling and query executions from db_config.py.
"""

from db_config import get_db_connection, execute_query
from psycopg2 import Error

def insert_apus_batch(apus_list: list) -> dict:
    """
    Inserts a list of APU insumo dicts into the database using a batch transaction.
    
    Args:
        apus_list (list): List of dictionaries containing APU insumo values.
        
    Returns:
        dict: Summary of success and any database error messages.
    """
    if not apus_list:
        return {"success": True, "count": 0, "errors": []}
        
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
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    # Convert list of dicts to list of tuples in the exact order required
    tuple_data = []
    for item in apus_list:
        # Standardize dates: Convert empty string '–' to None for DB insert
        fecha_aprob = item.get("fecha_aprobacion_apu")
        if fecha_aprob == "–": fecha_aprob = None
        
        fecha_analisis = item.get("fecha_analisis_apu")
        if fecha_analisis == "–": fecha_analisis = None
        
        # Standardize text fields
        def std_text(field_name):
            val = item.get(field_name)
            if val == "–": return None
            return val
            
        row = (
            fecha_aprob,
            fecha_analisis,
            std_text("ciudad"),
            std_text("pais"),
            std_text("entidad"),
            std_text("contratista"),
            std_text("nombre_proyecto"),
            std_text("numero_contrato"),
            std_text("item"),
            std_text("items_descripcion"),
            std_text("item_unidad"),
            item.get("precio_unitario"),
            item.get("precio_unitario_sin_aiu"),
            std_text("codigo_insumo"),
            std_text("tipo_insumo"),
            std_text("insumo_descripcion"),
            std_text("insumo_unidad"),
            item.get("rendimiento_insumo"),
            item.get("precio_unitario_apu"),
            item.get("precio_parcial_apu"),
            std_text("observacion"),
            std_text("link_documento")
        )
        tuple_data.append(row)
        
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # executemany is efficient for large batches
        cursor.executemany(sql, tuple_data)
        conn.commit()
        
        count = len(tuple_data)
        cursor.close()
        return {"success": True, "count": count, "errors": []}
        
    except Error as e:
        if conn:
            conn.rollback()
        error_msg = f"Database batch insertion failed: {e}"
        # Fallback to row-by-row insertion to pinpoint error
        print(f"⚠️ {error_msg}. Retrying row-by-row...")
        
        # Row-by-row insertion
        inserted_count = 0
        db_errors = [error_msg]
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            for i, row in enumerate(tuple_data):
                try:
                    cursor.execute(sql, row)
                    conn.commit()
                    inserted_count += 1
                except Error as re:
                    if conn:
                        conn.rollback()
                    db_errors.append(f"Row {i} (Project: {row[6]}, Item: {row[8]}): {re}")
            cursor.close()
        except Exception as conn_err:
            db_errors.append(f"Failed to reconnect: {conn_err}")
            
        return {
            "success": inserted_count > 0,
            "count": inserted_count,
            "errors": db_errors
        }
    finally:
        if conn:
            conn.close()

def get_unique_projects() -> list:
    """
    Retrieves all unique project names from the apus table.
    """
    query = """
        SELECT DISTINCT nombre_proyecto 
        FROM apus 
        WHERE nombre_proyecto IS NOT NULL AND nombre_proyecto != '–'
        ORDER BY nombre_proyecto;
    """
    try:
        results = execute_query(query, dict_cursor=False)
        return [row[0] for row in results]
    except Exception as e:
        print(f"❌ Error getting unique projects: {e}")
        return []

def get_apus(filters: dict = None, limit: int = 50, offset: int = 0) -> dict:
    """
    Retrieves APU rows with pagination and filters.
    
    Supported filters in dict:
        - nombre_proyecto (str, partial ILIKE match)
        - ciudad (str, partial ILIKE match)
        - items_descripcion (str, partial ILIKE match)
        - insumo_descripcion (str, partial ILIKE match)
        - tipo_insumo (str, exact match)
    """
    where_clauses = []
    params = []
    
    if filters:
        if filters.get("nombre_proyecto"):
            where_clauses.append("nombre_proyecto ILIKE %s")
            params.append(f"%{filters['nombre_proyecto']}%")
            
        if filters.get("ciudad"):
            where_clauses.append("ciudad ILIKE %s")
            params.append(f"%{filters['ciudad']}%")
            
        if filters.get("items_descripcion"):
            where_clauses.append("items_descripcion ILIKE %s")
            params.append(f"%{filters['items_descripcion']}%")
            
        if filters.get("insumo_descripcion"):
            where_clauses.append("insumo_descripcion ILIKE %s")
            params.append(f"%{filters['insumo_descripcion']}%")
            
        if filters.get("tipo_insumo"):
            where_clauses.append("tipo_insumo = %s")
            params.append(filters["tipo_insumo"])
            
    where_str = ""
    if where_clauses:
        where_str = "WHERE " + " AND ".join(where_clauses)
        
    # Query total count for pagination metadata
    count_query = f"SELECT COUNT(*) FROM apus {where_str};"
    
    # Query paginated rows
    query = f"""
        SELECT * 
        FROM apus 
        {where_str} 
        ORDER BY nombre_proyecto, item, id
        LIMIT %s OFFSET %s;
    """
    
    query_params = params + [limit, offset]
    
    try:
        total_count = execute_query(count_query, params=params if params else None, dict_cursor=False)[0][0]
        rows = execute_query(query, params=query_params, dict_cursor=True)
        
        # Serialize python datetimes to string for API comfort
        for row in rows:
            if row.get("fecha_aprobacion_apu"):
                row["fecha_aprobacion_apu"] = row["fecha_aprobacion_apu"].strftime("%Y-%m-%d")
            if row.get("fecha_analisis_apu"):
                row["fecha_analisis_apu"] = row["fecha_analisis_apu"].strftime("%Y-%m-%d")
            # Convert decimal fields to floats
            for key in ["precio_unitario", "precio_unitario_sin_aiu", "rendimiento_insumo", "precio_unitario_apu", "precio_parcial_apu"]:
                if row.get(key) is not None:
                    row[key] = float(row[key])
                    
        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "data": rows
        }
    except Exception as e:
        print(f"❌ Error querying APUs: {e}")
        return {"total": 0, "limit": limit, "offset": offset, "data": [], "error": str(e)}

def delete_project_apus(project_name: str) -> dict:
    """
    Deletes all APU rows belonging to a specific project.
    
    Args:
        project_name (str): The project name.
        
    Returns:
        dict: Success status and rows affected.
    """
    query = "DELETE FROM apus WHERE nombre_proyecto = %s;"
    try:
        affected = execute_query(query, params=(project_name,), fetch=False)
        return {"success": True, "rows_deleted": affected}
    except Exception as e:
        return {"success": False, "error": str(e)}
