"""
APU Service - Lógica de negocio robusta, optimizada y segura para Análisis de Precios Unitarios
"""

import logging
from typing import List, Dict, Any, Optional
from db_config import get_db_connection
from psycopg2.extras import RealDictCursor
from psycopg2 import Error as DatabaseError

log = logging.getLogger("mapus.backend.services.apu")

class ApuService:
    def __init__(self):
        # Lista blanca exacta de columnas (debe coincidir con nombres de tabla)
        self._allowed_sort_fields = {
            "id", "nombre_proyecto", "ciudad", "precio_unitario", 
            "contratista", "entidad", "fecha_aprobacion_apu", "precio_parcial_apu"
        }
        self._max_limit = 500

    def get_unique_projects(self) -> List[str]:
        """Recupera la lista única de proyectos."""
        query = "SELECT DISTINCT nombre_proyecto FROM apus WHERE nombre_proyecto IS NOT NULL ORDER BY nombre_proyecto"
        
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query)
                    results = cursor.fetchall()
                    return [r['nombre_proyecto'] for r in results]
        except DatabaseError:
            log.exception("Database error in get_unique_projects")
            raise

    def get_apus(
        self, 
        filters: Dict[str, Any], 
        limit: int = 50, 
        offset: int = 0,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """Consulta paginada, ordenada y filtrada dinámicamente."""
        
        # Refuerzo de límites (defense in depth)
        limit = min(max(1, limit), self._max_limit)
        offset = max(0, offset)
        
        where_clauses = []
        params = []

        text_filters = [
            'nombre_proyecto', 'ciudad', 'items_descripcion', 'insumo_descripcion',
            'tipo_insumo', 'contratista', 'entidad', 'codigo_insumo', 'item',
            'item_unidad', 'insumo_unidad', 'pais', 'numero_contrato'
        ]

        for field in text_filters:
            value = filters.get(field)
            if value:
                where_clauses.append(f"{field} ILIKE %s")
                params.append(f"%{str(value).strip()}%")

        if search:
            search_value = f"%{search.strip()}%"
            search_clause = (
                "(nombre_proyecto ILIKE %s OR "
                "items_descripcion ILIKE %s OR "
                "insumo_descripcion ILIKE %s OR "
                "contratista ILIKE %s)"
            )
            where_clauses.append(search_clause)
            params.extend([search_value] * 4)

        where_str = " AND ".join(where_clauses)
        where_str = f"WHERE {where_str}" if where_str else ""

        # Validación estricta de ordenamiento
        sort_column = "id"
        if sort_by:
            normalized = sort_by.strip().lower()
            if normalized in self._allowed_sort_fields:
                sort_column = normalized

        order_direction = "DESC" if str(sort_order).lower() == "desc" else "ASC"

        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    
                    # COUNT total
                    count_query = f"SELECT COUNT(*) FROM apus {where_str}"
                    cursor.execute(count_query, params)
                    total = cursor.fetchone()['count']

                    # SELECT paginado
                    query = f"""
                        SELECT * FROM apus 
                        {where_str}
                        ORDER BY {sort_column} {order_direction}
                        LIMIT %s OFFSET %s
                    """
                    cursor.execute(query, params + [limit, offset])
                    results = cursor.fetchall()

                    log.info("APU query executed", extra={
                        "total": total,
                        "returned": len(results),
                        "limit": limit,
                        "offset": offset,
                        "sort_by": sort_column,
                        "filters_count": len(where_clauses)
                    })

                    return {
                        "success": True,
                        "count": len(results),
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "data": results
                    }
        except DatabaseError:
            log.exception("Database error in get_apus")
            raise

    def delete_project_apus(self, nombre_proyecto: str) -> Dict[str, Any]:
        """Elimina todos los APUs de un proyecto en una transacción."""
        query = "DELETE FROM apus WHERE nombre_proyecto = %s"
        
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (nombre_proyecto,))
                    count = cursor.rowcount
                    conn.commit()
                    
                    log.warning("Eliminados %d registros de APU para proyecto: %s", count, nombre_proyecto)
                    return {
                        "success": True, 
                        "deleted": count,
                        "message": f"Se eliminaron {count} APUs de {nombre_proyecto}."
                    }
        except DatabaseError:
            log.exception("Database error deleting project: %s", nombre_proyecto)
            raise

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Obtiene métricas para el dashboard."""
        query = """
            SELECT 
                COUNT(*) as total_apus,
                COUNT(DISTINCT nombre_proyecto) as total_projects,
                COUNT(DISTINCT ciudad) as total_cities,
                AVG(precio_unitario) as avg_precio_unitario
            FROM apus
            WHERE precio_unitario IS NOT NULL
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query)
                    return cursor.fetchone()
        except DatabaseError:
            log.exception("Database error in get_dashboard_stats")
            raise

    def get_filter_options(self) -> Dict[str, List[str]]:
        """
        OPTIMIZACIÓN CRÍTICA (Opción B): Obtiene todas las opciones únicas de catálogo 
        en una ÚNICA llamada unificada a PostgreSQL para optimizar el round-trip por red.
        """
        query = """
            SELECT 
                COALESCE(json_agg(DISTINCT ciudad) FILTER (WHERE ciudad IS NOT NULL), '[]') as ciudad,
                COALESCE(json_agg(DISTINCT entidad) FILTER (WHERE entidad IS NOT NULL), '[]') as entidad,
                COALESCE(json_agg(DISTINCT contratista) FILTER (WHERE contratista IS NOT NULL), '[]') as contratista,
                COALESCE(json_agg(DISTINCT tipo_insumo) FILTER (WHERE tipo_insumo IS NOT NULL), '[]') as tipo_insumo,
                COALESCE(json_agg(DISTINCT pais) FILTER (WHERE pais IS NOT NULL), '[]') as pais
            FROM apus;
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query)
                    row = cursor.fetchone()
                    
                    # Despaquetamos los arreglos JSON nativos ordenándolos alfabéticamente para la interfaz
                    options = {
                        "ciudad": sorted(row["ciudad"]) if row else [],
                        "entidad": sorted(row["entidad"]) if row else [],
                        "contratista": sorted(row["contratista"]) if row else [],
                        "tipo_insumo": sorted(row["tipo_insumo"]) if row else [],
                        "pais": sorted(row["pais"]) if row else []
                    }
            
            log.info("Filter options retrieved via single atomic multi-query", extra={"fields": list(options.keys())})
            return options
        except DatabaseError:
            log.exception("Database error in get_filter_options")
            raise

# Instancia global de acceso a datos
apu_service = ApuService()