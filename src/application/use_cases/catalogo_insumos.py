"""
Application: Catálogo canónico de insumos e histórico de precios

Casos de uso:
  - backfill del catálogo desde el banco `apus` y desde las referencias SECOP,
  - consulta de estadísticas de precio/rendimiento por insumo.

El backfill está pensado para correr como job/mantenimiento (no en el request de
construcción de un APU).
"""

import logging
from typing import Optional

from src.infrastructure.database.connection import get_db_connection
from src.infrastructure.database.repositories.catalogo_insumos_repository import (
    catalogo_insumos_repo,
)

log = logging.getLogger("mapus.application.catalogo_insumos")


def estadisticas_insumo(descripcion: str, ciudad: Optional[str] = None) -> dict:
    """Estadísticas de precio y rendimiento de un insumo (mediana, rango, dato
    más reciente), resolviéndolo contra el catálogo canónico."""
    if not descripcion or len(descripcion.strip()) < 3:
        raise ValueError("Describe el insumo con al menos 3 caracteres")
    return catalogo_insumos_repo.estadisticas(descripcion, ciudad=ciudad)


def backfill_desde_banco(limite: Optional[int] = None, tam_lote: int = 500) -> dict:
    """Puebla insumo_maestro + precio_insumo_historico a partir de la tabla apus.

    Cada fila con insumo y precio se resuelve a un maestro y aporta una
    observación de precio (idempotente: re-ejecutar no duplica)."""
    procesadas = 0
    con_precio = 0
    offset = 0
    with get_db_connection() as conn:
        while True:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """SELECT numero_contrato, item, codigo_insumo, insumo_descripcion,
                              insumo_unidad, tipo_insumo, rendimiento_insumo,
                              precio_unitario_apu, ciudad, pais, fecha_aprobacion_apu
                       FROM apus
                       WHERE insumo_descripcion IS NOT NULL AND insumo_descripcion <> ''
                       ORDER BY id
                       LIMIT %s OFFSET %s""",
                    (tam_lote, offset),
                )
                filas = cur.fetchall()
            if not filas:
                break
            for f in filas:
                insumo_id = catalogo_insumos_repo.resolver_o_crear(
                    f["insumo_descripcion"], unidad=f.get("insumo_unidad"),
                    tipo_insumo=f.get("tipo_insumo"), codigo=f.get("codigo_insumo"),
                    fuente="banco", conn=conn,
                )
                procesadas += 1
                if insumo_id is None:
                    continue
                fecha = f.get("fecha_aprobacion_apu")
                fuente_id = "|".join(str(f.get(k) or "") for k in ("numero_contrato", "item", "codigo_insumo"))
                if catalogo_insumos_repo.registrar_precio(
                    insumo_id, f.get("precio_unitario_apu"), unidad=f.get("insumo_unidad"),
                    rendimiento=f.get("rendimiento_insumo"), ciudad=f.get("ciudad"),
                    fecha=str(fecha) if fecha else None, fuente="banco",
                    fuente_id=fuente_id, conn=conn,
                ):
                    con_precio += 1
            conn.commit()
            offset += len(filas)
            if limite and procesadas >= limite:
                break
    resumen = catalogo_insumos_repo.contar()
    log.info("Backfill banco: %d fila(s), %d con precio. Catálogo: %s", procesadas, con_precio, resumen)
    return {"success": True, "filas_procesadas": procesadas, "precios_registrados": con_precio,
            "catalogo": resumen}


def backfill_desde_referencias_externas(limite: Optional[int] = None, tam_lote: int = 500) -> dict:
    """Incorpora al histórico TODAS las referencias externas ya ingeridas
    (SECOP, IDU, INVÍAS, ...), resolviendo cada una contra el catálogo canónico."""
    procesadas = 0
    con_precio = 0
    offset = 0
    with get_db_connection() as conn:
        while True:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """SELECT fuente, fuente_id, descripcion, unidad, precio,
                              rendimiento, ciudad, departamento, fecha
                       FROM precio_referencia_externa
                       WHERE precio IS NOT NULL
                       ORDER BY id
                       LIMIT %s OFFSET %s""",
                    (tam_lote, offset),
                )
                filas = cur.fetchall()
            if not filas:
                break
            for f in filas:
                insumo_id = catalogo_insumos_repo.resolver_o_crear(
                    f["descripcion"], unidad=f.get("unidad"), fuente=f.get("fuente"), conn=conn,
                )
                procesadas += 1
                if insumo_id is None:
                    continue
                fecha = f.get("fecha")
                if catalogo_insumos_repo.registrar_precio(
                    insumo_id, f.get("precio"), unidad=f.get("unidad"),
                    rendimiento=f.get("rendimiento"), ciudad=f.get("ciudad"),
                    departamento=f.get("departamento"),
                    fecha=str(fecha) if fecha else None,
                    fuente=f.get("fuente") or "externa", fuente_id=f.get("fuente_id"),
                    conn=conn,
                ):
                    con_precio += 1
            conn.commit()
            offset += len(filas)
            if limite and procesadas >= limite:
                break
    resumen = catalogo_insumos_repo.contar()
    log.info("Backfill SECOP: %d fila(s), %d con precio. Catálogo: %s", procesadas, con_precio, resumen)
    return {"success": True, "filas_procesadas": procesadas, "precios_registrados": con_precio,
            "catalogo": resumen}
