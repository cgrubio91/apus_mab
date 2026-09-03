"""
Infrastructure: Repositorio de series de índices de costos (MySQL)

Persiste y lee la tabla `indice_costos` (serie, periodo 'YYYY-MM', valor). Sirve
de insumo para la indexación temporal de precios (ej. DANE ICCP / IPC).
"""

import logging

from src.infrastructure.database.connection import get_db_connection

log = logging.getLogger("mapus.infrastructure.indice_repo")


class IndiceCostosRepository:

    def upsert_serie(self, serie: str, puntos: list[tuple], fuente: str = "DANE") -> dict:
        """Inserta/actualiza puntos de una serie. `puntos`: [(periodo, valor)]."""
        serie = (serie or "").strip()
        if not serie or not puntos:
            return {"recibidos": 0, "afectados": 0}
        filas = []
        for periodo, valor in puntos:
            periodo = str(periodo).strip()[:7]
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                continue
            if len(periodo) != 7:
                continue
            filas.append((serie, periodo, str(valor), fuente))
        if not filas:
            return {"recibidos": len(puntos), "afectados": 0}
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO indice_costos (serie, periodo, valor, fuente)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE valor = VALUES(valor), fuente = VALUES(fuente)""",
                    filas,
                )
                afectados = cur.rowcount
                conn.commit()
        return {"recibidos": len(puntos), "afectados": afectados}

    def get_serie(self, serie: str) -> dict:
        """Devuelve la serie como {periodo: valor} lista para indexar."""
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    "SELECT periodo, valor FROM indice_costos WHERE serie = %s ORDER BY periodo",
                    (serie,),
                )
                return {r["periodo"]: float(r["valor"]) for r in cur.fetchall()}

    def series_disponibles(self) -> list:
        with get_db_connection() as conn:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """SELECT serie, COUNT(*) AS puntos, MIN(periodo) AS desde, MAX(periodo) AS hasta
                       FROM indice_costos GROUP BY serie ORDER BY serie"""
                )
                return cur.fetchall()


indice_costos_repo = IndiceCostosRepository()
