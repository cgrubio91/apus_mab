"""
Infrastructure: Repositorio de referencias de precio externas (MySQL)

Persiste y consulta la tabla `precio_referencia_externa`. La ingesta es
idempotente: se deduplica por `clave_unica` (fuente + id de la fuente), de modo
que re-ingerir la misma búsqueda ACTUALIZA en vez de duplicar.
"""

import logging
from typing import Optional

from src.domain.entities.referencia_externa import ReferenciaExterna
from src.infrastructure.database.connection import get_db_connection

log = logging.getLogger("mapus.infrastructure.ref_externa_repo")


class ReferenciaExternaRepository:

    def upsert_muchas(self, referencias: list[ReferenciaExterna]) -> dict:
        """Inserta o actualiza referencias por `clave_unica`. Devuelve conteos."""
        if not referencias:
            return {"recibidas": 0, "afectadas": 0}

        filas = []
        for r in referencias:
            filas.append((
                r.fuente, r.fuente_id, r.url, r.granularidad, r.descripcion,
                r.unidad, r.codigo,
                str(r.precio) if r.precio is not None else None,
                str(r.rendimiento) if r.rendimiento is not None else None,
                r.ciudad, r.departamento, r.entidad, r.proveedor,
                r.fecha.isoformat() if r.fecha else None,
                r.observacion, r.clave_unica(),
            ))

        sql = """
            INSERT INTO precio_referencia_externa
                (fuente, fuente_id, url, granularidad, descripcion, unidad, codigo,
                 precio, rendimiento, ciudad, departamento, entidad, proveedor,
                 fecha, observacion, clave_unica)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                url = VALUES(url),
                descripcion = VALUES(descripcion),
                unidad = VALUES(unidad),
                codigo = VALUES(codigo),
                precio = VALUES(precio),
                rendimiento = VALUES(rendimiento),
                ciudad = VALUES(ciudad),
                departamento = VALUES(departamento),
                entidad = VALUES(entidad),
                proveedor = VALUES(proveedor),
                fecha = VALUES(fecha),
                observacion = VALUES(observacion)
        """
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(sql, filas)
                afectadas = cursor.rowcount
                conn.commit()
        return {"recibidas": len(filas), "afectadas": afectadas}

    def buscar(self, descripcion: str, fuente: Optional[str] = None,
               ciudad: Optional[str] = None, limite: int = 20) -> list:
        """Busca referencias por palabras de la descripción (LIKE, tolerante),
        opcionalmente filtrando por fuente y ciudad. Ordena por recencia."""
        palabras = [p for p in (descripcion or "").split() if len(p) > 3][:6]
        if not palabras:
            return []
        condiciones = " OR ".join("descripcion LIKE %s" for _ in palabras)
        params: list = [f"%{p}%" for p in palabras]
        where = f"({condiciones})"
        if fuente:
            where += " AND fuente = %s"
            params.append(fuente)
        if ciudad and ciudad.strip():
            where += " AND ciudad LIKE %s"
            params.append(f"%{ciudad.strip()}%")
        params.append(max(1, min(int(limite), 100)))

        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(
                    f"""SELECT id, fuente, fuente_id, url, granularidad, descripcion,
                               unidad, codigo, precio, rendimiento, ciudad, departamento,
                               entidad, proveedor, fecha, observacion
                        FROM precio_referencia_externa
                        WHERE {where}
                        ORDER BY (fecha IS NULL), fecha DESC
                        LIMIT %s""",
                    params,
                )
                return cursor.fetchall()

    def contar(self, fuente: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM precio_referencia_externa"
        params: tuple = ()
        if fuente:
            sql += " WHERE fuente = %s"
            params = (fuente,)
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                return int(row["n"]) if row else 0


referencia_externa_repo = ReferenciaExternaRepository()
