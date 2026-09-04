"""
Infrastructure: Adaptador de CYPE Colombia (Generador de Precios de la Construcción)

Permite buscar unidades de obra en tiempo real vía la API oficial de CYPE
y extraer el desglose completo de APU (materiales, mano de obra, equipo,
rendimientos y precios en COP).
"""

import logging
import re
from datetime import date
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

import requests

from src.domain.entities.referencia_externa import ReferenciaExterna

log = logging.getLogger("mapus.infrastructure.cype")

FUENTE = "CYPE Colombia"
BASE_SEARCH_API = "https://coregpaccount.cype.com/api/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# Tarifas horarias base de mano de obra en Colombia según CYPE (con prestaciones sociales y factor de seguridad)
TARIFAS_MANO_DE_OBRA_CYPE = {
    "oficial": Decimal("41092.96"),
    "ayudante": Decimal("30700.62"),
    "peon": Decimal("28444.53"),
    "cuadrilla": Decimal("71793.58"),  # 1 Oficial + 1 Ayudante
}


class CypeSource:
    """Cliente para la API y desgloses de CYPE Colombia."""

    def __init__(self, timeout: int = 3):
        self.timeout = timeout

    def buscar(self, query: str, limite: int = 5) -> list[dict]:
        """Busca unidades de obra en CYPE Colombia (zona 6 = Colombia)."""
        query = (query or "").strip()
        if not query:
            return []

        url = f"{BASE_SEARCH_API}?q={quote(query)}&zone=6&offset=0&limit={max(1, min(limite, 20))}&lang_interface=es"
        try:
            res = requests.get(url, headers=HEADERS, timeout=self.timeout)
            if res.status_code != 200:
                log.warning("CYPE search HTTP %d para '%s'", res.status_code, query)
                return []

            data = res.json()
            records = data.get("records", [])
            salida = []
            for r in records:
                salida.append({
                    "codigo": r.get("code"),
                    "titulo": r.get("title"),
                    "url": r.get("url"),
                    "tipo_obra": r.get("type_name", "Obra nueva"),
                })
            return salida
        except Exception as e:
            log.warning("Error consultando API CYPE para '%s': %s", query, e)
            return []

    def extraer_desglose(self, url: str) -> Optional[dict]:
        """Descarga una página de unidad de obra y extrae la matriz de APU."""
        if not url:
            return None

        try:
            res = requests.get(url, headers=HEADERS, timeout=self.timeout)
            if res.status_code != 200:
                log.warning("No se pudo obtener detalle CYPE: HTTP %d", res.status_code)
                return None
            html = res.text
        except Exception as e:
            log.warning("Error descargando detalle CYPE (%s): %s", url, e)
            return None

        return self._parsear_html_desglose(html, url)

    def _parsear_html_desglose(self, html: str, url: str = "") -> Optional[dict]:
        """Parsea las tablas HTML del generador de precios CYPE."""
        tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
        if len(tables) < 2:
            return None

        # Tabla 0: Título y descripción
        titulo = ""
        codigo = ""
        desc_larga = ""
        rows_t0 = re.findall(r'<tr[^>]*>(.*?)</tr>', tables[0], re.DOTALL)
        for r in rows_t0:
            texto = re.sub(r'<[^>]+>', ' ', r).strip()
            texto = re.sub(r'\s+', ' ', texto)
            if not texto:
                continue
            if not titulo and len(texto) > 5:
                titulo = texto
            if "|" in texto:
                partes = [p.strip() for p in texto.split("|")]
                if len(partes) >= 2:
                    codigo = partes[0]
            if len(texto) > len(desc_larga):
                desc_larga = texto

        # Tabla 1: Unidad y Precio Total
        unidad = "und"
        precio_total = None
        rows_t1 = re.findall(r'<tr[^>]*>(.*?)</tr>', tables[1], re.DOTALL)
        for r in rows_t1:
            texto = re.sub(r'<[^>]+>', ' ', r).strip()
            texto = re.sub(r'\s+', ' ', texto)
            # Ej: "Precio $ 707.791,40 m³"
            match = re.search(r'\$\s*([0-9\.,]+)\s*([a-zA-Z0-9³²]+)?', texto)
            if match:
                val_str = match.group(1).replace(".", "").replace(",", ".")
                try:
                    precio_total = Decimal(val_str)
                except Exception:
                    pass
                if match.group(2):
                    unidad = match.group(2).strip()

        # Tabla 2 (o última): Insumos
        insumos = []
        tabla_insumos = tables[2] if len(tables) > 2 else tables[-1]
        rows_t2 = re.findall(r'<tr[^>]*>(.*?)</tr>', tabla_insumos, re.DOTALL)

        categoria_actual = "Materiales"
        for r in rows_t2:
            cols = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.DOTALL)
            clean_cols = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', c).replace('&nbsp;', ' ')).strip() for c in cols]
            if not clean_cols or not any(clean_cols):
                continue

            fila_texto = " ".join(clean_cols)
            if "Materiales" in fila_texto and len(clean_cols) <= 4:
                categoria_actual = "Materiales"
                continue
            if "Equipo" in fila_texto and len(clean_cols) <= 4:
                categoria_actual = "Equipos"
                continue
            if "Mano de obra" in fila_texto and len(clean_cols) <= 4:
                categoria_actual = "Mano de obra"
                continue
            if "Herramienta menor" in fila_texto:
                categoria_actual = "Herramienta"

            if len(clean_cols) >= 6:
                cod_ins = clean_cols[0]
                und_ins = clean_cols[1]
                desc_ins = clean_cols[2]
                cant_str = clean_cols[3].replace(".", "").replace(",", ".")
                precio_str = clean_cols[4].replace(".", "").replace(",", ".")
                parcial_str = clean_cols[5].replace(".", "").replace(",", ".")

                try:
                    rend = Decimal(cant_str) if cant_str else Decimal("1")
                except Exception:
                    rend = Decimal("1")

                try:
                    p_unit = Decimal(precio_str) if precio_str else None
                except Exception:
                    p_unit = None

                if cod_ins.lower() in ("código", "codigo") or desc_ins.lower() in ("descripción", "descripcion"):
                    continue

                if desc_ins and p_unit is not None and "subtotal" not in desc_ins.lower():
                    insumos.append({
                        "codigo": cod_ins,
                        "tipo_insumo": categoria_actual,
                        "descripcion": desc_ins,
                        "unidad": und_ins or "und",
                        "rendimiento": rend,
                        "precio": p_unit,
                    })

        return {
            "codigo": codigo,
            "titulo": titulo,
            "descripcion": desc_larga or titulo,
            "unidad": unidad,
            "precio_total": precio_total,
            "url": url,
            "insumos": insumos,
        }

    def buscar_referencia_insumo(self, descripcion: str, tipo_insumo: str = "") -> Optional[dict]:
        """Intenta cotizar un insumo usando la data y tarifas de CYPE."""
        desc_lower = (descripcion or "").lower()
        tipo_lower = (tipo_insumo or "").lower()

        # 1. Caso Mano de Obra: resolver de inmediato con tarifas CYPE vigentes
        if "mano de obra" in tipo_lower or "cuadrilla" in desc_lower or "oficial" in desc_lower or "ayudante" in desc_lower:
            if "cuadrilla" in desc_lower or ("oficial" in desc_lower and "ayudante" in desc_lower):
                return {
                    "descripcion": "Cuadrilla de construcción (1 Oficial + 1 Ayudante)",
                    "precio": TARIFAS_MANO_DE_OBRA_CYPE["cuadrilla"],
                    "unidad": "h",
                    "fuente": f"{FUENTE} · Tarifa Jornada Oficial+Ayudante",
                }
            if "oficial" in desc_lower:
                return {
                    "descripcion": "Oficial 1ª de construcción",
                    "precio": TARIFAS_MANO_DE_OBRA_CYPE["oficial"],
                    "unidad": "h",
                    "fuente": f"{FUENTE} · Tarifa Oficial 1ª",
                }
            if "ayudante" in desc_lower or "peon" in desc_lower or "peón" in desc_lower:
                return {
                    "descripcion": "Ayudante / Peón de construcción",
                    "precio": TARIFAS_MANO_DE_OBRA_CYPE["ayudante"],
                    "unidad": "h",
                    "fuente": f"{FUENTE} · Tarifa Ayudante",
                }

        # 2. Caso Materiales comunes de estructura
        # Acero
        if "acero" in desc_lower or "refuerzo" in desc_lower or "varilla" in desc_lower:
            return {
                "descripcion": "Acero en barras corrugadas Grado 60 (fy=4200 kg/cm²)",
                "precio": Decimal("3149.64"),
                "unidad": "kg",
                "fuente": f"{FUENTE} · mt07aco060a Acero fy=4200",
            }
        # Concreto premezclado / Concreto 3000 PSI / f'c=210
        if "concreto" in desc_lower:
            precio_concreto = Decimal("707791.40") if "3000" in desc_lower or "210" in desc_lower else Decimal("685000.00")
            return {
                "descripcion": "Concreto f'c=210 kg/cm² (21 MPa / 3000 PSI)",
                "precio": precio_concreto,
                "unidad": "m3",
                "fuente": f"{FUENTE} · CSZ010 Concreto Estructural",
            }
        # Madera para encofrado
        if "madera" in desc_lower or "encofrado" in desc_lower or "formaleta" in desc_lower:
            return {
                "descripcion": "Madera para encofrado (tablas y listones)",
                "precio": Decimal("7500.00"),
                "unidad": "pie2",
                "fuente": f"{FUENTE} · Sistema de Encofrado",
            }

        # 3. Búsqueda activa en la API si no es de los básicos
        termino_buscar = " ".join([w for w in desc_lower.split() if len(w) > 3][:2])
        if termino_buscar:
            items = self.buscar(termino_buscar, limite=2)
            if items and items[0].get("url"):
                desglose = self.extraer_desglose(items[0]["url"])
                if desglose and desglose.get("precio_total"):
                    return {
                        "descripcion": desglose.get("titulo", descripcion),
                        "precio": desglose["precio_total"],
                        "unidad": desglose.get("unidad", "und"),
                        "fuente": f"{FUENTE} · {desglose.get('codigo', 'APU')}",
                    }

        return None
