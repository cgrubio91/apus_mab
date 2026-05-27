"""
APU Service - Lógica de negocio para Análisis de Precios Unitarios
"""

from typing import List, Dict, Any, Optional
from db_config import get_db_connection
from psycopg2.extras import RealDictCursor

class ApuService:
    def __init__(self):
        pass

    def get_unique_projects(self) -> List[str]:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT DISTINCT nombre_proyecto FROM apus ORDER BY nombre_proyecto")
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return [r['nombre_proyecto'] for r in results if r['nombre_proyecto']]

    def get_apus(self, filters: Dict[str, Any], limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        where_clause = []
        params = []
        
        if filters.get('nombre_proyecto'):
            where_clause.append(f"nombre_proyecto ILIKE %s")
            params.append(f"%{filters['nombre_proyecto']}%")
        if filters.get('ciudad'):
            where_clause.append(f"ciudad ILIKE %s")
            params.append(f"%{filters['ciudad']}%")
        if filters.get('insumo_descripcion'):
            where_clause.append(f"insumo_descripcion ILIKE %s")
            params.append(f"%{filters['insumo_descripcion']}%")
        if filters.get('tipo_insumo'):
            where_clause.append(f"tipo_insumo ILIKE %s")
            params.append(f"%{filters['tipo_insumo']}%")
        
        where_str = " AND ".join(where_clause)
        if where_str:
            where_str = "WHERE " + where_str
        
        count_query = f"SELECT COUNT(*) FROM apus {where_str if where_str else ''}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()['count']
        
        query = f"""
            SELECT * FROM apus 
            {where_str if where_str else ''}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(query, params + [limit, offset])
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {"data": results, "total": total}

    def delete_project_apus(self, nombre_proyecto: str) -> Dict[str, Any]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM apus WHERE nombre_proyecto = %s", (nombre_proyecto,))
        count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        return {"success": True, "deleted": count}

apu_service = ApuService()