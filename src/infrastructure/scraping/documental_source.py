"""
Infrastructure: base para fuentes de precio DOCUMENTALES (IDU, INVÍAS, ...)

Muchas entidades publican sus listas de precios de referencia y APUs tipo como
documentos (PDF/Excel), no como API. Este módulo:

  1. descubre/recibe la URL del documento,
  2. lo descarga,
  3. lo pasa por el EXTRACTOR existente (src.infrastructure.ai.gemini_extractor),
  4. normaliza cada fila extraída a ReferenciaExterna (granularidad insumo/material).

El mapeo (`mapear_fila_extraida`) es una función PURA y se prueba sin red ni IA.
La descarga y la extracción se inyectan, de modo que el flujo también se prueba
con dobles de test.
"""

import logging
import os
import tempfile
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

import requests

from src.domain.entities.referencia_externa import ReferenciaExterna

log = logging.getLogger("mapus.infrastructure.documental")

_SESSION = requests.Session()


def _num(valor) -> Optional[Decimal]:
    if valor is None:
        return None
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d >= 0 else None


def mapear_fila_extraida(fila: dict, fuente: str, ciudad_defecto: Optional[str] = None,
                         fecha_defecto: Optional[str] = None,
                         fuente_id: Optional[str] = None) -> Optional[ReferenciaExterna]:
    """Convierte una fila del extractor (formato ApuRecord) en ReferenciaExterna.

    Prioriza el nivel INSUMO (lo valioso de estas fuentes: precio + rendimiento):
    usa insumo_descripcion y precio_unitario_apu; si la fila es solo de ítem, cae
    a items_descripcion y precio_unitario.
    """
    desc = (fila.get("insumo_descripcion") or fila.get("items_descripcion") or "").strip()
    if not desc:
        return None

    precio = _num(fila.get("precio_unitario_apu"))
    if precio is None:
        precio = _num(fila.get("precio_unitario"))
    rendimiento = _num(fila.get("rendimiento_insumo"))

    # granularidad: 'insumo' si hay señales de insumo (rendimiento o precio de insumo);
    # si no, 'material' (precio suelto de material/lista de precios).
    es_insumo = fila.get("insumo_descripcion") and (
        rendimiento is not None or fila.get("precio_unitario_apu") is not None
    )
    granularidad = "insumo" if es_insumo else "material"

    ciudad = (fila.get("ciudad") or "").strip() or ciudad_defecto
    fecha = (fila.get("fecha_aprobacion_apu") or fila.get("fecha_analisis_apu") or "").strip() or fecha_defecto

    return ReferenciaExterna(
        fuente=fuente,
        fuente_id=fuente_id,
        url=(fila.get("link_documento") or "").strip() or None,
        granularidad=granularidad,
        descripcion=desc,
        unidad=(fila.get("insumo_unidad") or fila.get("item_unidad") or "").strip() or None,
        codigo=(fila.get("codigo_insumo") or "").strip() or None,
        precio=precio,
        rendimiento=rendimiento,
        ciudad=ciudad,
        entidad=fuente,
        fecha=fecha,
        observacion=f"Extraído de documento de {fuente}.",
    )


def descargar_documento(url: str, timeout: int = 60) -> str:
    """Descarga un documento a un archivo temporal y devuelve su ruta.
    Conserva la extensión (.pdf/.xlsx/.xls) para que el extractor elija el parser."""
    resp = _SESSION.get(url, timeout=(15, timeout), stream=True)
    resp.raise_for_status()
    ext = os.path.splitext(url.split("?")[0])[1].lower() or ".pdf"
    if ext not in (".pdf", ".xlsx", ".xls", ".xlsm"):
        ext = ".pdf"
    fd, ruta = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
    return ruta


def _extraer_documento(ruta: str, filename: str) -> list[dict]:
    """Puente al extractor existente: elige parser por extensión y post-procesa."""
    from src.infrastructure.ai.gemini_extractor import (
        extract_apus_from_excel,
        extract_apus_from_pdf_multimodal,
        post_process_extracted_data,
    )
    ext = os.path.splitext(ruta)[1].lower()
    if ext in (".xlsx", ".xls", ".xlsm"):
        crudo = extract_apus_from_excel(ruta, filename)
    else:
        crudo = extract_apus_from_pdf_multimodal(ruta, filename)
    return post_process_extracted_data(crudo, filename)


class DocumentalSource:
    """Fuente documental genérica. Las subclases fijan FUENTE y ciudad por defecto."""

    FUENTE = "documental"
    CIUDAD_DEFECTO: Optional[str] = None

    def __init__(self, descargar: Optional[Callable] = None, extraer: Optional[Callable] = None):
        # Inyectables para pruebas (sin red ni IA).
        self._descargar = descargar or descargar_documento
        self._extraer = extraer or _extraer_documento

    def ingerir_documento(self, url: str, ciudad: Optional[str] = None,
                          fecha: Optional[str] = None) -> list[ReferenciaExterna]:
        """Descarga, extrae y normaliza un documento a referencias externas."""
        filename = os.path.basename(url.split("?")[0]) or f"{self.FUENTE}.pdf"
        ruta = self._descargar(url)
        try:
            filas = self._extraer(ruta, filename)
        finally:
            try:
                if os.path.exists(ruta):
                    os.remove(ruta)
            except OSError:
                log.warning("No se pudo borrar el temporal %s", ruta)

        referencias = []
        for fila in filas or []:
            ref = mapear_fila_extraida(
                fila, self.FUENTE, ciudad_defecto=ciudad or self.CIUDAD_DEFECTO,
                fecha_defecto=fecha, fuente_id=url,
            )
            if ref:
                referencias.append(ref)
        log.info("%s: documento %s → %d referencia(s)", self.FUENTE, filename, len(referencias))
        return referencias

    def ingerir_documentos(self, urls: list[str], ciudad: Optional[str] = None,
                           fecha: Optional[str] = None) -> list[ReferenciaExterna]:
        todas = []
        for url in urls:
            try:
                todas.extend(self.ingerir_documento(url, ciudad=ciudad, fecha=fecha))
            except Exception:
                log.exception("%s: falló la ingesta del documento %s", self.FUENTE, url)
        return todas
