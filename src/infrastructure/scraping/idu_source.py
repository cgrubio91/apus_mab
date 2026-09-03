"""
Infrastructure: Fuente IDU (Instituto de Desarrollo Urbano, Bogotá)

El IDU publica listas de precios de referencia (materiales, mano de obra, equipo,
transporte) y APUs de referencia como documentos PDF/Excel. Esta fuente reutiliza
el pipeline documental: descubre las URLs de los documentos vigentes y las pasa
por el extractor + normalización a ReferenciaExterna (ciudad por defecto: Bogotá).

Descubrimiento de URLs (en orden):
  1. Lista-semilla configurable por entorno (IDU_URLS_SEED, separadas por coma):
     robusta frente a rediseños del portal; tú la mantienes al cambiar la vigencia.
  2. URLs pasadas explícitamente a la ingesta.
El scraping del HTML del portal se deja como extensión futura (frágil); la
lista-semilla cubre el caso real con cero fragilidad.
"""

import logging
import os
from typing import Optional

from src.infrastructure.scraping.documental_source import DocumentalSource

log = logging.getLogger("mapus.infrastructure.idu")

FUENTE = "IDU"


def urls_semilla() -> list[str]:
    """URLs de documentos IDU configuradas en IDU_URLS_SEED (coma o espacio)."""
    raw = os.getenv("IDU_URLS_SEED", "")
    return [u.strip() for u in raw.replace("\n", ",").replace(" ", ",").split(",") if u.strip()]


class IduSource(DocumentalSource):
    FUENTE = FUENTE
    CIUDAD_DEFECTO = "Bogotá"

    def resolver_urls(self, urls: Optional[list[str]] = None) -> list[str]:
        """Combina las URLs explícitas con la lista-semilla, sin duplicados."""
        combinadas = list(urls or []) + urls_semilla()
        vistas, salida = set(), []
        for u in combinadas:
            if u and u not in vistas:
                vistas.add(u)
                salida.append(u)
        return salida
