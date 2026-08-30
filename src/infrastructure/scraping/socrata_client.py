"""
Infrastructure: Cliente Socrata (SODA 2.1)

Cliente mínimo para datasets Socrata como datos.gov.co (donde publica SECOP II).
Solo depende de `requests` (ya en requirements). No asume dataset específico:
recibe dominio + dataset id y una consulta SoQL como parámetros.

Notas de entorno:
  - Las peticiones salen por el proxy de egress; `requests` ya respeta el
    CA bundle vía REQUESTS_CA_BUNDLE. No se toca la verificación TLS.
  - Un App Token (gratuito) evita el throttling estricto de invitados. Se envía
    como header X-App-Token si está configurado (SOCRATA_APP_TOKEN).
"""

import logging
import os
import time
from typing import Optional

import requests

log = logging.getLogger("mapus.infrastructure.socrata")

_SESSION = requests.Session()


class SocrataError(RuntimeError):
    """Error consultando un dataset Socrata."""


class SocrataClient:
    def __init__(self, domain: Optional[str] = None, app_token: Optional[str] = None,
                 timeout: int = 40):
        self.domain = (domain or os.getenv("SOCRATA_DOMAIN", "www.datos.gov.co")).strip().rstrip("/")
        self.app_token = app_token if app_token is not None else os.getenv("SOCRATA_APP_TOKEN")
        self.timeout = timeout

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        token = (self.app_token or "").strip()
        if token:
            headers["X-App-Token"] = token
        return headers

    def _resource_url(self, dataset_id: str) -> str:
        return f"https://{self.domain}/resource/{dataset_id}.json"

    def query(self, dataset_id: str, params: dict, max_attempts: int = 3) -> list[dict]:
        """Ejecuta una consulta SoQL (params: $select, $where, $order, $limit...)
        y devuelve la lista de filas. Reintenta ante errores transitorios."""
        url = self._resource_url(dataset_id)
        last_exc: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                resp = _SESSION.get(url, params=params, headers=self._headers(),
                                    timeout=(15, self.timeout))
                if resp.status_code == 200:
                    data = resp.json()
                    if not isinstance(data, list):
                        raise SocrataError("Respuesta Socrata inesperada (no es una lista)")
                    return data
                # 4xx (menos 429) no se reintenta: es un error de la consulta.
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    raise SocrataError(f"Socrata {resp.status_code}: {resp.text[:300]}")
                last_exc = SocrataError(f"Socrata {resp.status_code}: {resp.text[:200]}")
            except (requests.RequestException, SocrataError) as e:
                last_exc = e
                log.warning("Socrata intento %d/%d falló: %s", attempt + 1, max_attempts, e)
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
        raise SocrataError(f"No se pudo consultar el dataset {dataset_id}: {last_exc}")

    def query_paginado(self, dataset_id: str, params: dict, max_total: int = 2000,
                       page_size: int = 1000) -> list[dict]:
        """Pagina con $limit/$offset hasta `max_total` filas. Requiere que `params`
        traiga un $order estable para que la paginación sea consistente."""
        base = dict(params)
        base.setdefault("$order", ":id")
        filas: list[dict] = []
        offset = 0
        while len(filas) < max_total:
            page = dict(base)
            page["$limit"] = min(page_size, max_total - len(filas))
            page["$offset"] = offset
            lote = self.query(dataset_id, page)
            if not lote:
                break
            filas.extend(lote)
            if len(lote) < page["$limit"]:
                break
            offset += len(lote)
        return filas
