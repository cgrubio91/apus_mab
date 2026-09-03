"""
Infrastructure: Catálogo de Materiales Comerciales en Vivo (Homecenter / Constructor)

Permite consultar precios de mercado al detal/mayorista en tiempo real
para materiales de obra (cemento, tubería, acero, aditivos, madera, etc.)
en pesos colombianos (COP).
"""

import json
import logging
import re
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

import requests

from src.domain.entities.referencia_externa import ReferenciaExterna

log = logging.getLogger("mapus.infrastructure.materiales")

FUENTE = "Constructor Homecenter"
SEARCH_URL = "https://www.homecenter.com.co/homecenter-co/search?Ntt="
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class CatalogoMaterialesSource:
    """Cliente para consultar precios reales de materiales de ferretería mayorista."""

    def __init__(self, timeout: int = 6):
        self.timeout = timeout

    def buscar_material(self, query: str, limite: int = 3) -> list[dict]:
        """Busca productos y precios en Homecenter Colombia."""
        query = (query or "").strip()
        if len(query) < 3:
            return []

        url = f"{SEARCH_URL}{quote(query)}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=self.timeout)
            if r.status_code != 200:
                log.warning("Homecenter HTTP %d para '%s'", r.status_code, query)
                return []

            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
            if not match:
                return []

            data = json.loads(match.group(1))
            raw_results = (
                data.get("props", {})
                .get("pageProps", {})
                .get("searchProps", {})
                .get("searchData", {})
                .get("results", [])
            )

            productos = []
            for p in raw_results[:limite]:
                nombre = p.get("displayName")
                marca = p.get("brand") or "Genérico"
                prices = p.get("prices", [{}])
                precio_num = prices[0].get("priceWithoutFormatting") if prices else None
                unidad = prices[0].get("unit") or "und"

                if nombre and precio_num:
                    productos.append({
                        "nombre": nombre,
                        "marca": marca,
                        "precio": Decimal(str(precio_num)),
                        "unidad": unidad,
                        "fuente": f"{FUENTE} · {marca}",
                    })
            return productos
        except Exception as e:
            log.warning("Error buscando material en Homecenter '%s': %s", query, e)
            return []
