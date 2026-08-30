"""
Infrastructure: Fuente SECOP II (Colombia Compra Eficiente vía datos.gov.co)

Trae contratos adjudicados del open data de SECOP II como referencias de precio
a NIVEL DE CONTRATO (objeto + valor + ciudad + fecha). El open data estructurado
NO expone el desglose de insumos ni los rendimientos —esos viven en los documentos
del proceso—, así que la granularidad de estas referencias es "contrato".

Diseño:
  - `construir_params` y `mapear_fila` son funciones PURAS (sin red): se prueban
    en unidad sin tocar la API ni la BD.
  - El mapeo es TOLERANTE a nombres de columna: los datasets Socrata cambian de
    esquema con el tiempo, así que cada campo lógico prueba varias claves.
  - El dataset id y el App Token se configuran por entorno.
"""

import logging
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from src.domain.entities.referencia_externa import ReferenciaExterna
from src.infrastructure.scraping.socrata_client import SocrataClient

log = logging.getLogger("mapus.infrastructure.secop")

FUENTE = "SECOP II"

# SECOP II - Contratos Electrónicos (datos.gov.co). Configurable por entorno.
DATASET_CONTRATOS = os.getenv("SECOP_DATASET_ID", "jbjy-vk9h")

# Nombres de columna candidatos por campo lógico (tolerante a drift de esquema).
_CAMPOS_TEXTO = ["objeto_del_contrato", "descripcion_del_proceso", "objeto_a_contratar"]
_CAMPOS_CIUDAD = ["ciudad", "ciudad_entidad", "municipio"]
_CAMPOS_DEPTO = ["departamento", "departamento_entidad"]
_CAMPOS_ENTIDAD = ["nombre_entidad", "entidad", "nombre_de_la_entidad"]
_CAMPOS_PROVEEDOR = ["proveedor_adjudicado", "nombre_del_proveedor", "proveedor",
                     "razon_social_del_contratista"]
_CAMPOS_VALOR = ["valor_del_contrato", "valor_total_adjudicacion", "valor_contrato",
                 "cuantia_proceso"]
_CAMPOS_FECHA = ["fecha_de_firma", "fecha_de_firma_del_contrato", "fecha_firma",
                 "fecha_de_publicacion_del"]
_CAMPOS_ID = ["id_contrato", "referencia_del_contrato", "referencia_contrato",
              "id_del_proceso", "constancia"]
_CAMPOS_URL = ["urlproceso", "url_del_proceso", "url"]
_CAMPOS_UNIDAD = ["unidad", "unidad_de_medida"]


def _soql_str(valor: str) -> str:
    """Literal de texto SoQL con comillas simples escapadas (duplicadas)."""
    return "'" + str(valor).replace("'", "''") + "'"


def construir_params(keyword: str, ciudad: Optional[str] = None,
                     desde_fecha: Optional[str] = None, limite: int = 200,
                     campo_texto: str = _CAMPOS_TEXTO[0],
                     campo_ciudad: str = _CAMPOS_CIUDAD[0],
                     campo_fecha: str = _CAMPOS_FECHA[0]) -> dict:
    """Construye los parámetros SoQL de la consulta (función pura).

    - `keyword` va como búsqueda de texto (`$q`, full-text del dataset).
    - `ciudad` y `desde_fecha` se filtran con `$where`.
    - El orden es por fecha descendente para priorizar lo más reciente.
    """
    keyword = (keyword or "").strip()
    if not keyword:
        raise ValueError("Se requiere un término de búsqueda (keyword)")

    where = []
    if ciudad and ciudad.strip():
        where.append(f"upper({campo_ciudad}) like upper({_soql_str('%' + ciudad.strip() + '%')})")
    if desde_fecha and desde_fecha.strip():
        where.append(f"{campo_fecha} >= {_soql_str(desde_fecha.strip())}")

    params: dict = {
        "$q": keyword,
        "$order": f"{campo_fecha} DESC",
        "$limit": max(1, min(int(limite), 1000)),
    }
    if where:
        params["$where"] = " AND ".join(where)
    return params


def _primero(row: dict, claves: list[str]) -> Optional[str]:
    for k in claves:
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _parse_decimal(valor) -> Optional[Decimal]:
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None
    # Quita símbolos de moneda, dejando dígitos, separadores y signo.
    s = re.sub(r"[^\d.,-]", "", s)
    if not s or s == "-":
        return None
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        # El separador que aparece de último es el decimal; el otro es de miles.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        # Varias comas → miles; una sola → decimal (estilo LATAM).
        s = s.replace(",", "") if s.count(",") > 1 else s.replace(",", ".")
    elif has_dot and s.count(".") > 1:
        # Varios puntos → separador de miles (ej. "1.250.000.000").
        s = s.replace(".", "")
    try:
        d = Decimal(s)
        return d if d >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def _parse_fecha(valor) -> Optional[date]:
    if not valor:
        return None
    s = str(valor).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:26] if "." in s else s[:19] if "T" in s or " " in s else s[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _extraer_url(row: dict) -> Optional[str]:
    for k in _CAMPOS_URL:
        v = row.get(k)
        if isinstance(v, dict):
            u = v.get("url") or v.get("Url")
            if u:
                return str(u).strip()
        elif isinstance(v, str) and v.strip():
            return v.strip()
    return None


def mapear_fila(row: dict) -> Optional[ReferenciaExterna]:
    """Convierte una fila cruda de SECOP en ReferenciaExterna (función pura).
    Devuelve None si la fila no tiene descripción utilizable."""
    descripcion = _primero(row, _CAMPOS_TEXTO)
    if not descripcion:
        return None
    return ReferenciaExterna(
        fuente=FUENTE,
        fuente_id=_primero(row, _CAMPOS_ID),
        url=_extraer_url(row),
        granularidad="contrato",
        descripcion=descripcion,
        unidad=_primero(row, _CAMPOS_UNIDAD),
        precio=_parse_decimal(_primero(row, _CAMPOS_VALOR)),
        rendimiento=None,
        ciudad=_primero(row, _CAMPOS_CIUDAD),
        departamento=_primero(row, _CAMPOS_DEPTO),
        entidad=_primero(row, _CAMPOS_ENTIDAD),
        proveedor=_primero(row, _CAMPOS_PROVEEDOR),
        fecha=_parse_fecha(_primero(row, _CAMPOS_FECHA)),
        observacion="Referencia a nivel de contrato (SECOP no expone insumos/rendimientos en open data).",
    )


class SecopSource:
    def __init__(self, client: Optional[SocrataClient] = None,
                 dataset_id: str = DATASET_CONTRATOS):
        self.client = client or SocrataClient()
        self.dataset_id = dataset_id

    def buscar(self, keyword: str, ciudad: Optional[str] = None,
               desde_fecha: Optional[str] = None, limite: int = 200) -> list[ReferenciaExterna]:
        """Busca contratos por término y devuelve referencias mapeadas."""
        params = construir_params(keyword, ciudad=ciudad, desde_fecha=desde_fecha, limite=limite)
        filas = self.client.query(self.dataset_id, params)
        referencias = []
        for row in filas:
            try:
                ref = mapear_fila(row)
            except Exception:
                log.warning("Fila SECOP no mapeable, se omite", exc_info=True)
                continue
            if ref:
                referencias.append(ref)
        log.info("SECOP: %d fila(s) → %d referencia(s) para '%s'", len(filas), len(referencias), keyword)
        return referencias
