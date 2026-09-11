"""Application: Constructor de APU — costos directos y desglose A.I.U.

Submódulo de `constructor_apu`: cálculo de costo directo y cascada de A.I.U.
Reexportado desde `constructor_apu` para compatibilidad.
"""

import logging
from typing import Optional

log = logging.getLogger("mapus.application.constructor_costos")


def _mediana(valores: list[float]) -> Optional[float]:
    """Mediana de una lista de números (None si está vacía)."""
    vals = sorted(v for v in valores if v is not None)
    if not vals:
        return None
    n = len(vals)
    medio = n // 2
    if n % 2:
        return float(vals[medio])
    return round((vals[medio - 1] + vals[medio]) / 2, 6)


def calcular_costo_directo(insumos: list[dict], exigir_precio: bool = False) -> float:
    """Suma precio × rendimiento. Acepta claves de propuesta IA o de filas de BD."""
    total = 0.0
    for i in insumos or []:
        precio = i.get("precio")
        if precio is None:
            precio = i.get("precio_unitario_apu")
        if precio is None and not exigir_precio:
            precio = i.get("precio_banco")
        rend = i.get("rendimiento")
        if rend is None:
            rend = i.get("rendimiento_insumo")
        try:
            p = float(precio) if precio is not None else 0.0
            r = float(rend) if rend is not None else 1.0
        except (TypeError, ValueError):
            continue
        if p > 0:
            total += p * r
    return round(total, 2)


def calcular_desglose_aiu(costo_directo: float, proyecto_id: Optional[int] = None,
                          porcentajes_custom: Optional[dict] = None) -> dict:
    """Calcula el desglose formal de A.I.U. (Administración, Imprevistos, Utilidad e IVA sobre Utilidad).
    Toma los porcentajes personalizados dados, los configurados en el proyecto o los valores estándar de obra en Colombia."""
    from src.infrastructure.database.connection import execute_query
    if isinstance(proyecto_id, dict) and porcentajes_custom is None:
        porcentajes_custom = proyecto_id
        proyecto_id = None

    pct_a = 15.0
    pct_i = 3.0
    pct_u = 5.0
    pct_iva = 19.0

    if porcentajes_custom and isinstance(porcentajes_custom, dict):
        if porcentajes_custom.get("administracion") is not None:
            pct_a = float(porcentajes_custom["administracion"])
        if porcentajes_custom.get("imprevistos") is not None:
            pct_i = float(porcentajes_custom["imprevistos"])
        if porcentajes_custom.get("utilidad") is not None:
            pct_u = float(porcentajes_custom["utilidad"])
        if porcentajes_custom.get("iva_utilidad") is not None:
            pct_iva = float(porcentajes_custom["iva_utilidad"])
    elif proyecto_id:
        try:
            rows = execute_query(
                "SELECT aiu_administracion, aiu_imprevistos, aiu_utilidad, aiu_iva_utilidad FROM proyectos WHERE id = %s",
                (proyecto_id,),
            )
            if rows:
                r = rows[0]
                pct_a = float(r["aiu_administracion"] if r["aiu_administracion"] is not None else 15.0)
                pct_i = float(r["aiu_imprevistos"] if r["aiu_imprevistos"] is not None else 3.0)
                pct_u = float(r["aiu_utilidad"] if r["aiu_utilidad"] is not None else 5.0)
                pct_iva = float(r["aiu_iva_utilidad"] if r["aiu_iva_utilidad"] is not None else 19.0)
        except Exception:
            log.warning("No se pudo obtener AIU del proyecto %s, usando valores por defecto", proyecto_id)

    cd = round(float(costo_directo or 0), 2)
    val_a = round(cd * (pct_a / 100.0), 2)
    val_i = round(cd * (pct_i / 100.0), 2)
    val_u = round(cd * (pct_u / 100.0), 2)
    val_iva_u = round(val_u * (pct_iva / 100.0), 2)
    total_aiu = round(val_a + val_i + val_u + val_iva_u, 2)
    costo_total = round(cd + total_aiu, 2)
    pct_aiu_total = round((total_aiu / cd) * 100.0, 2) if cd > 0 else 0.0

    return {
        "costo_directo": cd,
        "porcentajes": {
            "administracion": pct_a,
            "imprevistos": pct_i,
            "utilidad": pct_u,
            "iva_utilidad": pct_iva,
            "aiu_total_porcentaje": pct_aiu_total,
        },
        "valores": {
            "administracion": val_a,
            "imprevistos": val_i,
            "utilidad": val_u,
            "iva_utilidad": val_iva_u,
            "total_aiu": total_aiu,
            "costo_total": costo_total,
        },
        "subtotal_aiu": total_aiu,
        "costo_total": costo_total,
    }


def _cargar_serie_indice() -> dict:
    """Carga la serie de índices por defecto (DANE) para indexar precios. Devuelve
    {} si no hay BD/serie: la indexación se vuelve un no-op silencioso."""
    try:
        from src.config.settings import settings
        from src.infrastructure.database.repositories.indice_costos_repository import (
            indice_costos_repo,
        )
        return indice_costos_repo.get_serie(settings.DANE_ICCP_SERIE)
    except Exception:
        log.warning("No se pudo cargar la serie de índices; se usan precios nominales", exc_info=True)
        return {}


def _respuesta_propuesta(solicitud_id: int, solicitud: dict, propuesta: dict,
                         refs_ranked: Optional[list[dict]] = None,
                         porcentajes_aiu: Optional[dict] = None) -> dict:
    desglose_aiu = calcular_desglose_aiu(
        calcular_costo_directo(propuesta.get("insumos") or [], exigir_precio=True),
        proyecto_id=solicitud.get("proyecto_id"),
        porcentajes_custom=porcentajes_aiu,
    )
    payload = {
        "solicitud_id": solicitud_id,
        "propuesta": propuesta,
        "desglose_aiu": desglose_aiu,
    }
    if refs_ranked is not None:
        payload["referencias_usadas"] = [
            {"item": r.get("item"), "descripcion": r.get("items_descripcion"), "ciudad": r.get("ciudad"),
             "fecha": str(r.get("fecha")) if r.get("fecha") else None, "recencia": r.get("recencia"),
             "precio_unitario": float(r["precio_unitario"]) if r.get("precio_unitario") else None}
            for r in refs_ranked[:4]
        ]
    return payload
