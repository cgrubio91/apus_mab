"""
Infrastructure: Catálogo de Materiales Comerciales en Vivo (Homecenter / Constructor)

Permite consultar precios de mercado al detal/mayorista en tiempo real
para materiales de obra (cemento, tubería, acero, aditivos, madera, mampostería, etc.)
en pesos colombianos (COP).
"""

import json
import logging
import re
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

import requests

log = logging.getLogger("mapus.infrastructure.materiales")

FUENTE = "Homecenter"
SEARCH_URL = "https://www.homecenter.com.co/homecenter-co/search?Ntt="
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Sinónimos y equivalencias comunes en especificaciones de obra vs. comercio
_SINONIMOS = [
    (r"\bacero\s+(?:de\s+)?refuerzo\b", "varilla corrugada"),
    (r"\bacero\s+figurado\b", "varilla corrugada"),
    (r"\bvarilla\s+figurada\b", "varilla corrugada"),
    (r"\btuberia\s+pvc\s+u\.?m\.?\b", "tuberia pvc"),
    (r"\banillo\s+(?:de\s+)?caucho\s+para\s+sello\b", "empaque caucho tuberia"),
    (r"\banillo\s+(?:de\s+)?caucho\b", "empaque caucho"),
]

# Palabras de ruido en descripciones técnicas de APUs
_RUIDO = [
    r"\bu\.?m\.?\b", r"\be/i\b", r"\binc\.?\b", r"\bsum\.?\b", r"\bsuministro\s+e\s+instalacion\b",
    r"\bsuministro\b", r"\binstalacion\b", r"\bcolocacion\b", r"\btransporte\b",
    r"\b\(?\s*%\s*\)?", r"\bcorrugada/lisa\b",
]


class CatalogoMaterialesSource:
    """Cliente para consultar precios reales de materiales de ferretería mayorista y retail."""

    def __init__(self, timeout: int = 6):
        self.timeout = timeout
        self._cache: dict[str, list[dict]] = {}

    def _limpiar_query(self, query: str) -> str:
        """Limpia palabras de ruido técnico de APUs para mejorar la búsqueda en catálogo comercial."""
        q = query.lower().strip()
        for pat, rep in _SINONIMOS:
            q = re.sub(pat, rep, q, flags=re.IGNORECASE)
        for r in _RUIDO:
            q = re.sub(r, " ", q, flags=re.IGNORECASE)
        # Limpiar caracteres especiales excepto guiones o comillas de medidas
        q = re.sub(r"[^\w\s\"'/.-]", " ", q)
        q = re.sub(r"\s+", " ", q).strip()
        return q

    def buscar_material(self, query: str, limite: int = 3) -> list[dict]:
        """Busca productos y precios en Homecenter Colombia."""
        query = (query or "").strip()
        if len(query) < 3:
            return []

        cache_key = f"{query.lower()}:{limite}"
        if cache_key in self._cache:
            return self._cache[cache_key]

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
                product_id = p.get("productId")
                prices = p.get("prices", [{}])
                precio_num = prices[0].get("priceWithoutFormatting") if prices else None
                unidad = prices[0].get("unit") or "und"

                if product_id:
                    prod_url = f"https://www.homecenter.com.co/homecenter-co/product/{product_id}/"
                else:
                    prod_url = url

                if nombre and precio_num:
                    productos.append({
                        "nombre": nombre,
                        "marca": marca,
                        "precio": Decimal(str(precio_num)),
                        "unidad": unidad,
                        "fuente": f"{FUENTE} · {marca}",
                        "fuente_link": prod_url,
                        "product_id": product_id,
                    })

            self._cache[cache_key] = productos
            return productos
        except Exception as e:
            log.warning("Error buscando material en Homecenter '%s': %s", query, e)
            return []

    def buscar_referencia(self, desc: str, tipo: Optional[str] = None) -> Optional[dict]:
        """Busca la mejor referencia de precio comercial para una descripción de APU."""
        desc = (desc or "").strip()
        if not desc:
            return None

        # 1. Intentar con query procesada
        q_limpia = self._limpiar_query(desc)
        if q_limpia:
            res = self.buscar_material(q_limpia, limite=3)
            if res:
                return res[0]

        # 2. Si falló y la descripción original era distinta, probar con la original
        if desc.lower() != q_limpia:
            res = self.buscar_material(desc, limite=3)
            if res:
                return res[0]

        # 3. Probar con las primeras 2-3 palabras significativas (sustantivos clave)
        palabras = [p for p in q_limpia.split() if len(p) >= 3 and not p.isdigit()]
        if len(palabras) > 2:
            q_corta = " ".join(palabras[:2])
            res = self.buscar_material(q_corta, limite=3)
            if res:
                return res[0]

        return None

