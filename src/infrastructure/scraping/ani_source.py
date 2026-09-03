"""
Infrastructure: Fuente ANI (Agencia Nacional de Infraestructura vía datos.gov.co)

Trae concesiones y contratos viales/infraestructura del open data de la ANI vía Socrata
como referencias de precio a NIVEL DE PROYECTO/CONTRATO (objeto, valor, entidad, fecha).
La granularidad es "contrato".
"""

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from src.config.settings import settings
from src.domain.entities.referencia_externa import ReferenciaExterna
from src.infrastructure.scraping.socrata_client import SocrataClient

log = logging.getLogger("mapus.infrastructure.ani")

FUENTE = "ANI"

# Campos candidatos tolerantes a drift de esquema en Socrata
_CAMPOS_TEXTO = [
    "objeto_del_proyecto", "objeto_proyecto", "nombre_proyecto", "proyecto",
    "descripcion", "objeto_del_contrato", "objeto", "concesion", "nombre_concesion"
]
_CAMPOS_CIUDAD = ["municipio", "ciudad", "origen_destino", "tramo", "zona"]
_CAMPOS_DEPTO = ["departamento", "departamentos", "region"]
_CAMPOS_ENTIDAD = ["entidad", "entidad_concedente", "concedente"]
_CAMPOS_PROVEEDOR = [
    "concesionario", "nombre_concesionario", "contratista", "adjudicatario",
    "razon_social", "sociedad_concesionaria"
]
_CAMPOS_VALOR = [
    "valor_inversion", "valor_estimado_inversion", "capex", "valor_contrato",
    "costo_total_inversion", "valor_total", "valor_adjudicado", "cuantia"
]
_CAMPOS_FECHA = [
    "fecha_firma_contrato", "fecha_inicio", "fecha_adjudicacion", "fecha_firma",
    "fecha_suscripcion", "fecha_de_firma"
]
_CAMPOS_ID = [
    "numero_contrato", "contrato", "codigo_proyecto", "id_proyecto",
    "codigo_concesion", "identificador"
]
_CAMPOS_URL = ["url_contrato", "enlace", "link", "url"]


def _soql_str(valor: str) -> str:
    """Literal de texto SoQL con comillas simples escapadas."""
    return "'" + str(valor).replace("'", "''") + "'"


def construir_params(keyword: str, ciudad: Optional[str] = None,
                     limite: int = 200,
                     campo_ciudad: str = _CAMPOS_CIUDAD[0]) -> dict:
    keyword = (keyword or "").strip()
    if not keyword:
        raise ValueError("Se requiere un término de búsqueda (keyword)")

    params: dict = {
        "$q": keyword,
        "$limit": max(1, min(int(limite), 1000)),
    }
    where = []
    if ciudad and ciudad.strip():
        where.append(f"upper({campo_ciudad}) like upper({_soql_str('%' + ciudad.strip() + '%')})")
    if where:
        params["$where"] = " AND ".join(where)

    return params


def _primero(row: dict, claves: list[str]) -> Optional[str]:
    for k in claves:
        v = row.get(k)
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    return None


def _parse_decimal(valor) -> Optional[Decimal]:
    if valor is None:
        return None
    s = str(valor).strip()
    if not s or s == "-":
        return None
    s = re.sub(r"[^\d.,-]", "", s)
    if not s or s == "-":
        return None
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        s = s.replace(",", "") if s.count(",") > 1 else s.replace(",", ".")
    elif has_dot and s.count(".") > 1:
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
    descripcion = _primero(row, _CAMPOS_TEXTO)
    if not descripcion:
        return None
    entidad = _primero(row, _CAMPOS_ENTIDAD) or "Agencia Nacional de Infraestructura (ANI)"
    return ReferenciaExterna(
        fuente=FUENTE,
        fuente_id=_primero(row, _CAMPOS_ID),
        url=_extraer_url(row),
        granularidad="contrato",
        descripcion=descripcion,
        unidad=None,
        precio=_parse_decimal(_primero(row, _CAMPOS_VALOR)),
        rendimiento=None,
        ciudad=_primero(row, _CAMPOS_CIUDAD),
        departamento=_primero(row, _CAMPOS_DEPTO),
        entidad=entidad,
        proveedor=_primero(row, _CAMPOS_PROVEEDOR),
        fecha=_parse_fecha(_primero(row, _CAMPOS_FECHA)),
        observacion="Referencia a nivel de contrato/concesión ANI.",
    )


class AniSource:
    def __init__(self, client: Optional[SocrataClient] = None,
                 dataset_id: Optional[str] = None):
        self.client = client or SocrataClient()
        self.dataset_id = dataset_id or settings.ANI_DATASET_ID

    def buscar(self, keyword: str, ciudad: Optional[str] = None,
               limite: int = 200) -> list[ReferenciaExterna]:
        params = construir_params(keyword, ciudad=ciudad, limite=limite)
        filas = self.client.query(self.dataset_id, params)
        referencias = []
        for row in filas:
            try:
                ref = mapear_fila(row)
            except Exception:
                log.warning("Fila ANI no mapeable, se omite", exc_info=True)
                continue
            if ref:
                referencias.append(ref)
        log.info("ANI: %d fila(s) → %d referencia(s) para '%s'", len(filas), len(referencias), keyword)
        return referencias
