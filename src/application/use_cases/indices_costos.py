"""
Application: Índices de costos (DANE) e indexación de precios

- Ingesta de una serie de índices desde DANE (Socrata) o carga manual.
- Estadísticas de precio de un insumo llevadas a pesos de HOY con la serie.

La indexación permite comparar una cotización actual contra precios históricos
del banco/SECOP/IDU/INVÍAS en términos reales (no nominales).
"""

import logging
from typing import Optional

from src.infrastructure.database.repositories.catalogo_insumos_repository import (
    catalogo_insumos_repo,
)
from src.infrastructure.database.repositories.indice_costos_repository import (
    indice_costos_repo,
)
from src.infrastructure.pricing.catalogo_helpers import estadisticas_precio
from src.infrastructure.pricing.indexacion import indexar_observaciones
from src.infrastructure.scraping.dane_source import DaneSource

log = logging.getLogger("mapus.application.indices")


def ingerir_dane(dataset_id: str, serie: str, campo_periodo: Optional[str] = None,
                 campo_valor: Optional[str] = None, where: Optional[str] = None,
                 source: Optional[DaneSource] = None) -> dict:
    """Descarga una serie de índices desde un dataset DANE (Socrata) y la guarda."""
    if not dataset_id or not serie:
        raise ValueError("Se requieren dataset_id y nombre de serie")
    src = source or DaneSource()
    puntos = src.obtener_serie(dataset_id, campo_periodo=campo_periodo,
                               campo_valor=campo_valor, where=where)
    resultado = indice_costos_repo.upsert_serie(serie, puntos, fuente="DANE")
    log.info("Ingesta DANE '%s': %d punto(s), %d afectado(s)",
             serie, len(puntos), resultado.get("afectados", 0))
    return {"success": True, "serie": serie, "puntos": len(puntos),
            "afectados": resultado.get("afectados", 0),
            "muestra": puntos[-6:]}


def cargar_serie_manual(serie: str, datos: dict) -> dict:
    """Carga una serie manualmente desde un dict {periodo: valor} (ej. copiado de
    la publicación DANE cuando no está en Socrata)."""
    if not serie or not datos:
        raise ValueError("Se requieren serie y datos {periodo: valor}")
    puntos = [(p, v) for p, v in datos.items()]
    resultado = indice_costos_repo.upsert_serie(serie, puntos, fuente="DANE-manual")
    return {"success": True, "serie": serie, "puntos": len(puntos),
            "afectados": resultado.get("afectados", 0)}


def series_disponibles() -> list:
    return indice_costos_repo.series_disponibles()


def estadisticas_insumo_indexadas(descripcion: str, serie: str,
                                  ciudad: Optional[str] = None) -> dict:
    """Estadísticas de precio de un insumo en pesos de HOY: cada observación se
    ajusta con la serie antes de agregar. Incluye también las cifras nominales."""
    if not descripcion or len(descripcion.strip()) < 3:
        raise ValueError("Describe el insumo con al menos 3 caracteres")

    insumo_id = catalogo_insumos_repo.resolver_por_descripcion(descripcion)
    if insumo_id is None:
        return {"encontrado": False, "insumo_id": None, "serie": serie,
                "nominal": estadisticas_precio([]), "indexado": estadisticas_precio([])}

    observaciones = catalogo_insumos_repo.observaciones_precio(insumo_id, ciudad=ciudad)
    serie_valores = indice_costos_repo.get_serie(serie)
    nominal = estadisticas_precio(observaciones)
    if not serie_valores:
        return {"encontrado": True, "insumo_id": insumo_id, "serie": serie,
                "serie_disponible": False, "nominal": nominal, "indexado": nominal}

    indexadas = indexar_observaciones(observaciones, serie_valores)
    return {"encontrado": True, "insumo_id": insumo_id, "serie": serie,
            "serie_disponible": True,
            "periodo_destino": max(serie_valores),
            "nominal": nominal,
            "indexado": estadisticas_precio(indexadas)}
