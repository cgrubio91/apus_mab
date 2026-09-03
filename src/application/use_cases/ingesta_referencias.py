"""
Application: Ingesta y consulta de referencias de precio externas

Orquesta la traída de datos externos (hoy SECOP II) y su persistencia en el
banco de referencias externas, además de la consulta para el Constructor de APU.

La ingesta está pensada para correr FUERA del camino crítico del request
(un job/cron), no dentro de la construcción de un APU.
"""

import logging
from typing import Optional

from src.infrastructure.database.repositories.referencia_externa_repository import (
    referencia_externa_repo,
)
from src.infrastructure.scraping.secop_source import FUENTE as FUENTE_SECOP
from src.infrastructure.scraping.secop_source import SecopSource

log = logging.getLogger("mapus.application.ingesta_referencias")


def ingerir_secop(keyword: str, ciudad: Optional[str] = None,
                  desde_fecha: Optional[str] = None, limite: int = 200,
                  source: Optional[SecopSource] = None) -> dict:
    """Busca en SECOP II por término y guarda las referencias (idempotente).

    Args:
        keyword: término de búsqueda (objeto del contrato).
        ciudad: filtro opcional de ciudad/municipio.
        desde_fecha: 'YYYY-MM-DD' para acotar a lo más reciente.
        limite: máximo de contratos a traer (<= 1000).
    """
    keyword = (keyword or "").strip()
    if len(keyword) < 3:
        raise ValueError("El término de búsqueda debe tener al menos 3 caracteres")

    src = source or SecopSource()
    referencias = src.buscar(keyword, ciudad=ciudad, desde_fecha=desde_fecha, limite=limite)
    resultado = referencia_externa_repo.upsert_muchas(referencias)
    log.info("Ingesta SECOP '%s': %d referencia(s) traída(s), %d fila(s) afectada(s)",
             keyword, len(referencias), resultado.get("afectadas", 0))
    return {
        "success": True,
        "fuente": FUENTE_SECOP,
        "keyword": keyword,
        "referencias_traidas": len(referencias),
        "filas_afectadas": resultado.get("afectadas", 0),
        "muestra": [r.model_dump(mode="json") for r in referencias[:10]],
    }


def consultar_referencias(descripcion: str, fuente: Optional[str] = None,
                          ciudad: Optional[str] = None, limite: int = 20) -> list:
    """Consulta referencias externas ya ingeridas (para mostrar junto al banco)."""
    return referencia_externa_repo.buscar(descripcion, fuente=fuente, ciudad=ciudad, limite=limite)


def buscar_cype(query: str, limite: int = 5) -> list[dict]:
    """Busca unidades de obra en tiempo real en CYPE Colombia."""
    from src.infrastructure.scraping.cype_source import CypeSource
    src = CypeSource()
    return src.buscar(query, limite=limite)


def extraer_desglose_cype(url: str) -> Optional[dict]:
    """Extrae el desglose completo de un APU desde CYPE Colombia."""
    from src.infrastructure.scraping.cype_source import CypeSource
    src = CypeSource()
    return src.extraer_desglose(url)

