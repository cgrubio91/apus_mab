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


import hashlib
from datetime import date
from src.domain.entities.referencia_externa import ReferenciaExterna
from src.infrastructure.scraping.ani_source import AniSource, FUENTE as FUENTE_ANI
from src.infrastructure.scraping.catalogo_materiales import CatalogoMaterialesSource, FUENTE as FUENTE_HOMECENTER
from src.infrastructure.scraping.cype_source import CypeSource, FUENTE as FUENTE_CYPE


def ingerir_cype(query: str, limite: int = 5, source: Optional[CypeSource] = None) -> dict:
    """Busca unidades de obra en CYPE Colombia, extrae sus desgloses de insumos y
    los guarda como referencias externas con granularidad='insumo'."""
    query = (query or "").strip()
    if len(query) < 3:
        raise ValueError("El término de búsqueda debe tener al menos 3 caracteres")

    src = source or CypeSource()
    unidades = src.buscar(query, limite=limite)
    referencias: list[ReferenciaExterna] = []

    for item in unidades:
        url = item.get("url")
        if not url:
            continue
        desglose = src.extraer_desglose(url)
        if not desglose:
            continue

        codigo_obra = desglose.get("codigo") or item.get("codigo") or "CYPE"
        titulo_obra = desglose.get("titulo") or item.get("titulo") or query

        insumos = desglose.get("insumos") or []
        if insumos:
            for ins in insumos:
                cod_ins = ins.get("codigo") or ins.get("descripcion", "")[:40]
                referencias.append(
                    ReferenciaExterna(
                        fuente=FUENTE_CYPE,
                        fuente_id=f"{codigo_obra}::{cod_ins}",
                        url=url,
                        granularidad="insumo",
                        descripcion=ins["descripcion"],
                        unidad=ins.get("unidad"),
                        codigo=ins.get("codigo"),
                        precio=ins.get("precio"),
                        rendimiento=ins.get("rendimiento"),
                        entidad="CYPE Ingenieros",
                        fecha=date.today(),
                        observacion=f"Desglose de APU: {titulo_obra} ({codigo_obra})",
                    )
                )
        elif desglose.get("precio_total"):
            # Si no hubo desglose detallado de insumos pero sí precio unitario total
            referencias.append(
                ReferenciaExterna(
                    fuente=FUENTE_CYPE,
                    fuente_id=codigo_obra,
                    url=url,
                    granularidad="contrato",
                    descripcion=titulo_obra,
                    unidad=desglose.get("unidad", "und"),
                    codigo=codigo_obra,
                    precio=desglose.get("precio_total"),
                    entidad="CYPE Ingenieros",
                    fecha=date.today(),
                    observacion="Unidad de obra completa generada por CYPE Colombia",
                )
            )

    resultado = referencia_externa_repo.upsert_muchas(referencias)
    log.info("Ingesta CYPE '%s': %d unidad(es), %d referencia(s), %d afectada(s)",
             query, len(unidades), len(referencias), resultado.get("afectadas", 0))
    return {
        "success": True,
        "fuente": FUENTE_CYPE,
        "query": query,
        "unidades_consultadas": len(unidades),
        "referencias_traidas": len(referencias),
        "filas_afectadas": resultado.get("afectadas", 0),
        "muestra": [r.model_dump(mode="json") for r in referencias[:10]],
    }


def ingerir_homecenter(query: str, limite: int = 5,
                       source: Optional[CatalogoMaterialesSource] = None) -> dict:
    """Busca materiales en Constructor Homecenter y los persiste como referencias externas
    con granularidad='material'."""
    query = (query or "").strip()
    if len(query) < 3:
        raise ValueError("El término de búsqueda debe tener al menos 3 caracteres")

    src = source or CatalogoMaterialesSource()
    materiales = src.buscar_material(query, limite=limite)
    referencias: list[ReferenciaExterna] = []

    for mat in materiales:
        nombre = mat.get("nombre", "").strip()
        marca = mat.get("marca", "").strip() or "Genérico"
        # Hash estable de nombre + marca como fuente_id idempotente
        fuente_id = hashlib.md5(f"{nombre.lower()}|{marca.lower()}".encode("utf-8")).hexdigest()
        referencias.append(
            ReferenciaExterna(
                fuente=FUENTE_HOMECENTER,
                fuente_id=fuente_id,
                url=None,
                granularidad="material",
                descripcion=nombre,
                unidad=mat.get("unidad") or "und",
                precio=mat.get("precio"),
                proveedor=f"Homecenter ({marca})",
                fecha=date.today(),
                observacion=f"Material de catálogo mayorista/retail Homecenter. Marca: {marca}",
            )
        )

    resultado = referencia_externa_repo.upsert_muchas(referencias)
    log.info("Ingesta Homecenter '%s': %d material(es), %d afectada(s)",
             query, len(referencias), resultado.get("afectadas", 0))
    return {
        "success": True,
        "fuente": FUENTE_HOMECENTER,
        "query": query,
        "referencias_traidas": len(referencias),
        "filas_afectadas": resultado.get("afectadas", 0),
        "muestra": [r.model_dump(mode="json") for r in referencias[:10]],
    }


def ingerir_ani(keyword: str, ciudad: Optional[str] = None,
                limite: int = 200, source: Optional[AniSource] = None) -> dict:
    """Busca contratos/concesiones en ANI (datos.gov.co) y los persiste como referencias
    con granularidad='contrato'."""
    keyword = (keyword or "").strip()
    if len(keyword) < 3:
        raise ValueError("El término de búsqueda debe tener al menos 3 caracteres")

    src = source or AniSource()
    referencias = src.buscar(keyword, ciudad=ciudad, limite=limite)
    resultado = referencia_externa_repo.upsert_muchas(referencias)
    log.info("Ingesta ANI '%s': %d referencia(s) traída(s), %d afectada(s)",
             keyword, len(referencias), resultado.get("afectadas", 0))
    return {
        "success": True,
        "fuente": FUENTE_ANI,
        "keyword": keyword,
        "referencias_traidas": len(referencias),
        "filas_afectadas": resultado.get("afectadas", 0),
        "muestra": [r.model_dump(mode="json") for r in referencias[:10]],
    }


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


