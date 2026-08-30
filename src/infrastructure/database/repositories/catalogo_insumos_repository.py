"""
Infrastructure: Repositorio del catálogo canónico de insumos (MySQL)

Resuelve descripciones libres a un insumo_maestro (vía sinónimo exacto o firma
de tokens), acumula el histórico de precios y calcula estadísticas. Es la capa
que reemplaza el emparejamiento texto-contra-texto por una resolución única.
"""

import logging
from typing import Optional

import mysql.connector

from src.infrastructure.database.connection import get_db_connection
from src.infrastructure.pricing.catalogo_helpers import (
    descripcion_normalizada,
    estadisticas_precio,
    firma_insumo,
)

log = logging.getLogger("mapus.infrastructure.catalogo_repo")


class CatalogoInsumosRepository:

    # ── Resolución canónica ──────────────────────────────────────────

    def resolver_por_descripcion(self, descripcion: str, conn=None) -> Optional[int]:
        """Devuelve el id de insumo_maestro para una descripción, SIN crearlo.
        Busca primero por sinónimo exacto (normalizado) y luego por firma."""
        norm = descripcion_normalizada(descripcion)
        firma = firma_insumo(descripcion) or norm
        if not norm and not firma:
            return None
        cerrar = conn is None
        conn = conn or get_db_connection()
        try:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    "SELECT insumo_maestro_id AS id FROM insumo_sinonimo WHERE descripcion_norm = %s",
                    (norm,),
                )
                row = cur.fetchone()
                if row:
                    return int(row["id"])
                cur.execute("SELECT id FROM insumo_maestro WHERE firma = %s", (firma,))
                row = cur.fetchone()
                return int(row["id"]) if row else None
        finally:
            if cerrar:
                conn.close()

    def resolver_o_crear(self, descripcion: str, unidad: Optional[str] = None,
                         tipo_insumo: Optional[str] = None, codigo: Optional[str] = None,
                         fuente: Optional[str] = None, conn=None) -> Optional[int]:
        """Resuelve el insumo_maestro y, si no existe, lo crea. Registra siempre
        el sinónimo (la descripción original) para acelerar futuras resoluciones."""
        descripcion = (descripcion or "").strip()
        if not descripcion:
            return None
        norm = descripcion_normalizada(descripcion)
        firma = firma_insumo(descripcion) or norm
        if not firma:
            return None

        cerrar = conn is None
        conn = conn or get_db_connection()
        try:
            insumo_id = self.resolver_por_descripcion(descripcion, conn=conn)
            if insumo_id is None:
                with conn.cursor() as cur:
                    try:
                        cur.execute(
                            """INSERT INTO insumo_maestro (descripcion_canonica, firma, unidad, tipo_insumo, codigo)
                               VALUES (%s, %s, %s, %s, %s)""",
                            (descripcion[:300], firma[:300], unidad, tipo_insumo, codigo),
                        )
                        insumo_id = cur.lastrowid
                    except mysql.connector.IntegrityError:
                        # Carrera: otro proceso creó la misma firma.
                        cur.execute("SELECT id FROM insumo_maestro WHERE firma = %s", (firma,))
                        r = cur.fetchone()
                        insumo_id = int(r[0]) if r else None
            if insumo_id is not None:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT IGNORE INTO insumo_sinonimo
                               (insumo_maestro_id, descripcion_norm, descripcion_original, fuente)
                           VALUES (%s, %s, %s, %s)""",
                        (insumo_id, norm, descripcion[:300], fuente),
                    )
            if cerrar:
                conn.commit()
            return insumo_id
        except Exception:
            if cerrar:
                conn.rollback()
            raise
        finally:
            if cerrar:
                conn.close()

    # ── Histórico de precios ─────────────────────────────────────────

    def registrar_precio(self, insumo_id: int, precio, unidad: Optional[str] = None,
                         rendimiento=None, ciudad: Optional[str] = None,
                         departamento: Optional[str] = None, fecha: Optional[str] = None,
                         fuente: str = "banco", fuente_id: Optional[str] = None,
                         conn=None) -> bool:
        """Inserta una observación de precio (idempotente por clave_unica)."""
        try:
            precio = float(precio)
        except (TypeError, ValueError):
            return False
        if precio <= 0:
            return False
        clave = f"{fuente}::{fuente_id or ''}::{insumo_id}::{fecha or ''}::{ciudad or ''}"
        cerrar = conn is None
        conn = conn or get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO precio_insumo_historico
                           (insumo_maestro_id, precio, unidad, rendimiento, ciudad,
                            departamento, fecha, fuente, fuente_id, clave_unica)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE precio = VALUES(precio),
                           rendimiento = VALUES(rendimiento), unidad = VALUES(unidad)""",
                    (insumo_id, str(precio), unidad,
                     str(rendimiento) if rendimiento is not None else None,
                     ciudad, departamento, fecha, fuente, fuente_id, clave[:255]),
                )
            if cerrar:
                conn.commit()
            return True
        except Exception:
            if cerrar:
                conn.rollback()
            raise
        finally:
            if cerrar:
                conn.close()

    def observaciones_precio(self, insumo_id: int, ciudad: Optional[str] = None,
                             limite: int = 500) -> list:
        params: list = [insumo_id]
        where = "insumo_maestro_id = %s"
        if ciudad and ciudad.strip():
            where += " AND ciudad LIKE %s"
            params.append(f"%{ciudad.strip()}%")
        params.append(max(1, min(int(limite), 2000)))
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    f"""SELECT precio, fecha, ciudad, rendimiento, fuente
                        FROM precio_insumo_historico
                        WHERE {where}
                        ORDER BY (fecha IS NULL), fecha DESC
                        LIMIT %s""",
                    params,
                )
                return cur.fetchall()

    def estadisticas(self, descripcion: str, ciudad: Optional[str] = None) -> dict:
        """Resuelve el insumo y devuelve sus estadísticas de precio (mediana,
        rango, precio más reciente). n=0 si el insumo no está en el catálogo."""
        insumo_id = self.resolver_por_descripcion(descripcion)
        if insumo_id is None:
            return {"encontrado": False, "insumo_id": None,
                    **estadisticas_precio([])}
        obs = self.observaciones_precio(insumo_id, ciudad=ciudad)
        return {"encontrado": True, "insumo_id": insumo_id,
                "rendimiento_mediana": _mediana_rend(obs), **estadisticas_precio(obs)}

    def contar(self) -> dict:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cur:
                cur.execute("SELECT COUNT(*) AS n FROM insumo_maestro")
                insumos = cur.fetchone()["n"]
                cur.execute("SELECT COUNT(*) AS n FROM precio_insumo_historico")
                precios = cur.fetchone()["n"]
        return {"insumos_maestro": int(insumos), "observaciones_precio": int(precios)}


def _mediana_rend(observaciones: list) -> Optional[float]:
    from src.infrastructure.pricing.catalogo_helpers import mediana
    return mediana([o.get("rendimiento") for o in observaciones if o.get("rendimiento") is not None])


catalogo_insumos_repo = CatalogoInsumosRepository()
