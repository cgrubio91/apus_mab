"""
Infrastructure: Fuente INVÍAS (Instituto Nacional de Vías)

INVÍAS publica listas de precios de referencia por regional/territorial y APUs
tipo como documentos PDF/Excel. Reutiliza el pipeline documental igual que IDU;
la diferencia es que NO fija una ciudad por defecto (varía por regional), así que
la ciudad se toma de la fila extraída o se pasa explícitamente en la ingesta.
"""

import logging
import os
from typing import Optional

from src.config.settings import settings
from src.infrastructure.scraping.documental_source import DocumentalSource

log = logging.getLogger("mapus.infrastructure.invias")

FUENTE = "INVÍAS"


def urls_semilla() -> list[str]:
    """URLs de documentos INVÍAS configuradas en INVIAS_URLS_SEED."""
    raw = os.getenv("INVIAS_URLS_SEED") or settings.INVIAS_URLS_SEED or ""
    return [u.strip() for u in raw.replace("\n", ",").replace(" ", ",").split(",") if u.strip()]


class InviasSource(DocumentalSource):
    FUENTE = FUENTE
    CIUDAD_DEFECTO = None  # depende de la regional; se resuelve por fila/parámetro

    def resolver_urls(self, urls: Optional[list[str]] = None) -> list[str]:
        combinadas = list(urls or []) + urls_semilla()
        vistas, salida = set(), []
        for u in combinadas:
            if u and u not in vistas:
                vistas.add(u)
                salida.append(u)
        return salida
