"""
Infrastructure: Adaptador de CYPE Colombia (Generador de Precios de la Construcción)

Permite buscar unidades de obra en tiempo real vía la API oficial de CYPE
y extraer el desglose completo de APU (materiales, mano de obra, equipo,
rendimientos y precios en COP).
"""

import logging
import re
import time
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

import requests

from src.domain.entities.referencia_externa import ReferenciaExterna

log = logging.getLogger("mapus.infrastructure.cype")

FUENTE = "CYPE Colombia"
BASE_SEARCH_API = "https://coregpaccount.cype.com/api/search"
# Portada del generador de precios de Colombia, como enlace de respaldo.
# (OJO: "generadordeprecios.info/obra_nueva/Colombia.html" responde 404 desde 2026.)
BASE_WEB = "https://colombia.generadordeprecios.info/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# Prefijo del código CYPE → categoría. Es más fiable que leer los encabezados de sección
# del HTML, que a veces faltan y dejaban la mano de obra clasificada como "Materiales".
_PREFIJO_TIPO = {"mo": "Mano de obra", "mq": "Equipos", "mt": "Materiales"}

# Caché en memoria: una propuesta cotiza ~8 insumos y muchos caen en la misma unidad de
# obra, así que sin esto se repetirían las mismas descargas dentro de una sola petición.
_CACHE_TTL = 3600  # segundos
_CACHE_BUSQUEDAS: dict[str, tuple[float, list]] = {}
_CACHE_DESGLOSES: dict[str, tuple[float, Optional[dict]]] = {}


def _cache_get(cache: dict, clave: str):
    entrada = cache.get(clave)
    if entrada and (time.time() - entrada[0]) < _CACHE_TTL:
        return entrada[1]
    cache.pop(clave, None)
    return None


def _cache_set(cache: dict, clave: str, valor) -> None:
    cache[clave] = (time.time(), valor)


def clasificar_por_codigo(codigo: str, por_defecto: str = "Materiales") -> str:
    """Categoría del insumo a partir del prefijo de su código CYPE (mo/mq/mt)."""
    return _PREFIJO_TIPO.get((codigo or "").strip().lower()[:2], por_defecto)


# Límites de la búsqueda en vivo: cotizar ~8 insumos no puede disparar decenas de
# descargas, o la petición del usuario se vuelve inaceptablemente lenta.
_MAX_TERMINOS = 2
_MAX_UNIDADES_POR_TERMINO = 2
_UMBRAL_COINCIDENCIA = 0.5   # fracción mínima de palabras en común
_UMBRAL_ALTERNATIVO = 0.6    # exigencia mayor cuando la descripción no encabeza igual

_ES_MANO_DE_OBRA = re.compile(r"mano de obra|cuadrilla|oficial|ayudante|pe[oó]n|maestro", re.IGNORECASE)
_PALABRAS_VACIAS = {"para", "tipo", "con", "sin", "por", "los", "las", "del", "una", "uno"}


def _tokens_ordenados(texto: str) -> list:
    """Como _tokens pero conservando el orden de aparición."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    vistos, salida = set(), []
    for w in re.findall(r"[a-z0-9]+", t):
        if len(w) > 2 and w not in _PALABRAS_VACIAS and w not in vistos:
            vistos.add(w)
            salida.append(w)
    return salida


def _tokens(texto: str) -> set:
    """Palabras significativas, sin tildes ni signos, para comparar descripciones."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return {w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 2 and w not in _PALABRAS_VACIAS}


class CypeSource:
    """Cliente para la API y desgloses de CYPE Colombia."""

    def __init__(self, timeout: int = 3):
        self.timeout = timeout

    def buscar(self, query: str, limite: int = 5) -> list[dict]:
        """Busca unidades de obra en CYPE Colombia (zona 6 = Colombia)."""
        query = (query or "").strip()
        if not query:
            return []

        clave_cache = f"{query.lower()}|{limite}"
        en_cache = _cache_get(_CACHE_BUSQUEDAS, clave_cache)
        if en_cache is not None:
            return en_cache

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
            _cache_set(_CACHE_BUSQUEDAS, clave_cache, salida)
            return salida
        except Exception as e:
            log.warning("Error consultando API CYPE para '%s': %s", query, e)
            return []

    def extraer_desglose(self, url: str) -> Optional[dict]:
        """Descarga una página de unidad de obra y extrae la matriz de APU."""
        if not url:
            return None

        en_cache = _cache_get(_CACHE_DESGLOSES, url)
        if en_cache is not None:
            return en_cache

        try:
            res = requests.get(url, headers=HEADERS, timeout=self.timeout)
            if res.status_code != 200:
                log.warning("No se pudo obtener detalle CYPE: HTTP %d", res.status_code)
                return None
            # CYPE no declara charset en la cabecera y requests asume latin-1; sin esto
            # las descripciones llegan como "OficiaI 1Âª" o "tixotrÃ³pico".
            res.encoding = "utf-8"
            html = res.text
        except Exception as e:
            log.warning("Error descargando detalle CYPE (%s): %s", url, e)
            return None

        desglose = self._parsear_html_desglose(html, url)
        _cache_set(_CACHE_DESGLOSES, url, desglose)
        return desglose

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
                        "tipo_insumo": clasificar_por_codigo(cod_ins, categoria_actual),
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
        """Cotiza un insumo consultando CYPE en vivo.

        No hay precios escritos en el código: si CYPE no responde o no se encuentra el
        insumo se devuelve None, y el llamador sigue con la cascada (banco de APUs,
        catálogo comercial, SECOP) en vez de mostrar una cifra sin respaldo.
        """
        desc = (descripcion or "").strip()
        if not desc:
            return None

        objetivo = _tokens(desc)
        if not objetivo:
            return None
        # Palabra principal = primer sustantivo de la descripción ("Acero de refuerzo…").
        ordenados = _tokens_ordenados(desc)
        principal = ordenados[0] if ordenados else ""

        for termino in self._terminos_busqueda(desc, tipo_insumo):
            for item in self.buscar(termino, limite=_MAX_UNIDADES_POR_TERMINO):
                url = item.get("url")
                if not url:
                    continue
                desglose = self.extraer_desglose(url)
                if not desglose or not desglose.get("insumos"):
                    continue

                mejor = self._mejor_coincidencia(desglose["insumos"], objetivo, tipo_insumo, principal)
                if mejor:
                    codigo = mejor.get("codigo") or "insumo"
                    return {
                        "descripcion": mejor.get("descripcion") or desc,
                        "precio": mejor["precio"],
                        "unidad": mejor.get("unidad") or "und",
                        "fuente": f"{FUENTE} · {codigo}",
                        # Página real de la que se extrajo el precio: el soporte verificable.
                        "url": url,
                    }

        log.info("CYPE sin coincidencia en vivo para '%s'", desc[:60])
        return None

    def _terminos_busqueda(self, descripcion: str, tipo_insumo: str = "") -> list[str]:
        """Términos a probar contra la API, del más específico al más general.

        La API busca unidades de obra, no insumos sueltos, así que para un insumo
        genérico ("Oficial") hace falta caer en una unidad de obra que lo contenga.
        """
        palabras = [w for w in re.findall(r"[^\W\d_]+", descripcion, re.UNICODE)
                    if len(w) > 3 and w.lower() not in _PALABRAS_VACIAS]
        terminos = []
        if palabras:
            terminos.append(" ".join(palabras[:2]))
            if len(palabras) > 1:
                terminos.append(palabras[0])
        # La mano de obra y la herramienta aparecen en el desglose de casi cualquier
        # unidad de obra, así que un término de obra corriente sirve de ancla.
        if _ES_MANO_DE_OBRA.search(f"{descripcion} {tipo_insumo}"):
            terminos.append("concreto estructural")
        vistos, salida = set(), []
        for t in terminos:
            if t and t not in vistos:
                vistos.add(t)
                salida.append(t)
        return salida[:_MAX_TERMINOS]

    @staticmethod
    def _mejor_coincidencia(insumos: list[dict], objetivo: set, tipo_insumo: str = "",
                            principal: str = "") -> Optional[dict]:
        """Insumo del desglose que mejor corresponde al que se está cotizando.

        Se acepta un candidato si nombra el mismo material de entrada (su descripción
        ARRANCA con la palabra principal buscada) o si cubre casi todas las palabras.
        Sin esa condición, "acero de refuerzo" traía un perfil tubular "de acero
        galvanizado" y "concreto 3000 PSI" una grama sintética.
        """
        tipo_norm = (tipo_insumo or "").strip().lower()
        mejor, mejor_score = None, 0.0
        for ins in insumos:
            precio = ins.get("precio")
            if precio is None or precio <= 0:
                continue
            # La "herramienta menor" de CYPE es un % sobre la mano de obra, no un precio
            # unitario: tomarla daría cifras como "$4.111.866 %".
            if (ins.get("unidad") or "").strip() in ("%", "%%"):
                continue
            desc_ins = ins.get("descripcion") or ""
            tokens_ins = _tokens(desc_ins)
            if not tokens_ins:
                continue
            comunes = objetivo & tokens_ins
            if not comunes:
                continue

            lexico = len(comunes) / len(objetivo)
            # ¿La descripción EMPIEZA nombrando lo mismo? (p.ej. "Acero en barras…").
            # Tiene que ser la primera palabra: si se acepta en cualquiera de las
            # primeras posiciones, "Tornillo de acero" empata con "Acero en barras".
            tokens_ordenados_ins = _tokens_ordenados(desc_ins)
            encabeza = bool(principal) and bool(tokens_ordenados_ins) and tokens_ordenados_ins[0] == principal
            if not encabeza and lexico < _UMBRAL_ALTERNATIVO:
                continue

            score = lexico + (0.5 if encabeza else 0.0)
            # Coincidir en categoría solo desempata entre candidatos ya aceptados.
            if tipo_norm and clasificar_por_codigo(ins.get("codigo") or "").lower() == tipo_norm:
                score += 0.25
            if score > mejor_score:
                mejor, mejor_score = ins, score
        return mejor
