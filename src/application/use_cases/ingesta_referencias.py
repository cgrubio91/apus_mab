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
from src.infrastructure.scraping.idu_source import IduSource
from src.infrastructure.scraping.invias_source import InviasSource
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


def _ingerir_documental(src, seed_env: str, urls: Optional[list],
                        ciudad: Optional[str], fecha: Optional[str]) -> dict:
    """Flujo común de ingesta de fuentes documentales (IDU, INVÍAS): resuelve
    URLs, extrae, normaliza y persiste (idempotente por clave_unica)."""
    resueltas = src.resolver_urls(urls)
    if not resueltas:
        raise ValueError(
            f"No hay URLs de documentos de {src.FUENTE}. Pásalas en la petición o "
            f"configúralas en {seed_env}."
        )
    referencias = src.ingerir_documentos(resueltas, ciudad=ciudad, fecha=fecha)
    resultado = referencia_externa_repo.upsert_muchas(referencias)
    log.info("Ingesta %s: %d documento(s), %d referencia(s), %d afectada(s)",
             src.FUENTE, len(resueltas), len(referencias), resultado.get("afectadas", 0))
    return {
        "success": True,
        "fuente": src.FUENTE,
        "documentos": len(resueltas),
        "referencias_traidas": len(referencias),
        "filas_afectadas": resultado.get("afectadas", 0),
        "muestra": [r.model_dump(mode="json") for r in referencias[:10]],
    }


def ingerir_idu(urls: Optional[list] = None, ciudad: Optional[str] = None,
                fecha: Optional[str] = None, source: Optional[IduSource] = None) -> dict:
    """Ingiere documentos de precios del IDU (PDF/Excel). Si no se pasan `urls`,
    usa la lista-semilla IDU_URLS_SEED del entorno."""
    return _ingerir_documental(source or IduSource(), "IDU_URLS_SEED", urls, ciudad, fecha)


def ingerir_invias(urls: Optional[list] = None, ciudad: Optional[str] = None,
                   fecha: Optional[str] = None, source: Optional[InviasSource] = None) -> dict:
    """Ingiere documentos de precios de INVÍAS (PDF/Excel). Si no se pasan `urls`,
    usa la lista-semilla INVIAS_URLS_SEED del entorno."""
    return _ingerir_documental(source or InviasSource(), "INVIAS_URLS_SEED", urls, ciudad, fecha)


def consultar_referencias(descripcion: str, fuente: Optional[str] = None,
                          ciudad: Optional[str] = None, limite: int = 20) -> list:
    """Consulta referencias externas ya ingeridas (para mostrar junto al banco)."""
    return referencia_externa_repo.buscar(descripcion, fuente=fuente, ciudad=ciudad, limite=limite)
