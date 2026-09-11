"""
Application: Análisis APU — motor de comparación contra el banco.

Agrupa insumos por ítem, compara cotizaciones/proveedores, fija referencias
del banco de APUs y sube insumos sueltos. Sin llamadas directas a la IA
(esas viven en `analisis_ia`).
"""

import logging

from src.infrastructure.database.repositories.analisis_repository import (
    analisis_repo,
    _tokenizar,
    _similitud_tokens,
)

log = logging.getLogger("mapus.application.analisis_comparacion")


def _agrupar_por_item(insumos: list[dict]) -> list[dict]:
    """Agrupa las filas de insumo de la solicitud en APUs (un APU por ítem/cotización).

    Cada APU resultante tiene su cabecera (ítem, descripción, unidad, precio ofertado)
    y la lista de insumos que lo componen.
    """
    grupos: dict = {}
    orden: list = []
    for ins in insumos:
        clave = (
            ins.get("grupo_cotizacion", 1),
            (ins.get("item") or "").strip(),
            (ins.get("items_descripcion") or "").strip(),
        )
        if clave not in grupos:
            grupos[clave] = {
                "grupo_cotizacion": ins.get("grupo_cotizacion", 1),
                "nombre_archivo": ins.get("nombre_archivo", ""),
                "item": (ins.get("item") or "").strip(),
                "descripcion": (ins.get("items_descripcion") or "").strip(),
                "unidad": (ins.get("item_unidad") or "").strip(),
                "precio_ofertado": 0.0,
                "insumos": [],
            }
            orden.append(clave)
        apu = grupos[clave]
        precio = float(ins.get("precio_unitario") or 0)
        # El precio del ítem se repite en cada fila de insumo: nos quedamos con el mayor válido.
        if precio > apu["precio_ofertado"]:
            apu["precio_ofertado"] = precio
        if ins.get("codigo_insumo") or ins.get("insumo_descripcion") or ins.get("rendimiento_insumo") is not None:
            apu["insumos"].append({
                "tipo_insumo": ins.get("tipo_insumo") or "",
                "codigo_insumo": ins.get("codigo_insumo") or "",
                "insumo_descripcion": ins.get("insumo_descripcion") or "",
                "insumo_unidad": ins.get("insumo_unidad") or "",
                "rendimiento_insumo": ins.get("rendimiento_insumo"),
                "precio_unitario_apu": ins.get("precio_unitario_apu"),
                "precio_parcial_apu": ins.get("precio_parcial_apu"),
            })

    # Fallback: si la IA no extrajo precio_unitario del ítem, se calcula de los insumos.
    for apu in grupos.values():
        if apu["precio_ofertado"] == 0.0 and apu["insumos"]:
            total = sum(
                float(i.get("precio_parcial_apu") or 0) or
                (float(i.get("rendimiento_insumo") or 0) * float(i.get("precio_unitario_apu") or 0))
                for i in apu["insumos"]
            )
            if total > 0:
                apu["precio_ofertado"] = round(total, 2)
    return [grupos[k] for k in orden]


def _analizar_apu_con_banco(apu: dict) -> dict:
    descripcion = apu.get("descripcion", "")
    precio_ofertado = float(apu.get("precio_ofertado") or 0)

    resultado = {
        # Campos de nivel ítem (compatibles con export y firma legal):
        "item": apu.get("item", ""),
        "descripcion": descripcion,
        "unidad": apu.get("unidad", ""),
        "precio_ofertado": precio_ofertado,
        "grupo_cotizacion": apu.get("grupo_cotizacion", 1),
        "nombre_archivo": apu.get("nombre_archivo", ""),
        "mejor_precio_banco": None,
        "diferencia_precio": None,
        "diferencia_pct": None,
        "existe_en_banco": False,
        "item_banco_encontrado": None,
        "estructura_insumos_coincide": None,
        "rendimiento_coincide": None,
        "observaciones": "Sin descripción para comparar" if not descripcion else "",
        "recomendacion": "pendiente",
        # Detalle nuevo:
        "insumos_cotizados": apu.get("insumos", []),
        "candidatos": [],
    }

    if not descripcion:
        return resultado

    insumos_desc = [i.get("insumo_descripcion") for i in apu.get("insumos", []) if i.get("insumo_descripcion")]
    candidatos = analisis_repo.buscar_apus_similares(descripcion, insumos_desc=insumos_desc)
    resultado["existe_en_banco"] = len(candidatos) > 0

    if candidatos:
        for c in candidatos:
            pb = float(c.get("precio_unitario") or 0)
            c["diferencia_precio"] = round(precio_ofertado - pb, 2) if pb else None
            c["diferencia_pct"] = round((precio_ofertado - pb) / pb * 100, 1) if pb else None
            c["es_match_ia"] = False
            # Marca cada insumo del candidato: verde si el APU cotizado lo tiene, rojo si no.
            _marcar_equivalencias(c.get("insumos"), apu.get("insumos"))

        # La REFERENCIA es el APU más similar (candidatos vienen ordenados por similitud).
        _fijar_referencia(resultado, candidatos[0], precio_ofertado)
        candidatos[0]["es_referencia"] = True
        resultado["candidatos"] = candidatos
        # Marca los insumos cotizados contra el candidato más similar.
        _marcar_equivalencias(resultado["insumos_cotizados"], candidatos[0].get("insumos"))

    # Importación diferida: analisis_ia importa helpers de este módulo a nivel
    # superior, así que importar _analisis_apu_con_ia arriba crearía un ciclo.
    from src.application.use_cases.analisis_ia import _analisis_apu_con_ia

    resultado = _analisis_apu_con_ia(apu, candidatos, resultado)
    return resultado


def _fijar_referencia(resultado: dict, candidato: dict, precio_ofertado: float) -> None:
    """Fija el APU del banco usado como referencia (precio, ítem, diferencia)."""
    pb = float(candidato.get("precio_unitario") or 0)
    resultado["item_banco_encontrado"] = candidato.get("item", "")
    resultado["mejor_precio_banco"] = pb or None
    if pb:
        resultado["diferencia_precio"] = round(precio_ofertado - pb, 2)
        resultado["diferencia_pct"] = round((precio_ofertado - pb) / pb * 100, 1)
    else:
        resultado["diferencia_precio"] = None
        resultado["diferencia_pct"] = None


def _marcar_equivalencias(a_marcar: list, referencia: list, umbral: float = 0.34) -> None:
    """Marca cada insumo de `a_marcar` con `equivalente=True` si hay un insumo parecido
    en `referencia` (por similitud de descripción). Verde = equivalente, rojo = no está."""
    if not a_marcar:
        return
    ref_tokens = [_tokenizar(r.get("insumo_descripcion") or "") for r in (referencia or [])]
    for ins in a_marcar:
        ti = _tokenizar(ins.get("insumo_descripcion") or "")
        mejor = max((_similitud_tokens(ti, tr) for tr in ref_tokens), default=0.0)
        ins["equivalente"] = mejor >= umbral


def _comparar_cotizaciones(items_analizados: list[dict]) -> dict:
    """Compara las cotizaciones (grupos) por precio total y promedio de sus ítems."""
    grupos: dict = {}
    for it in items_analizados:
        g = it.get("grupo_cotizacion", 1)
        if g not in grupos:
            grupos[g] = {"total": 0.0, "count": 0, "archivo": it.get("nombre_archivo") or f"Cotización {g}"}
        grupos[g]["total"] += float(it.get("precio_ofertado") or 0)
        grupos[g]["count"] += 1

    mejor_grupo = None
    mejor_promedio = float("inf")
    for g, info in grupos.items():
        info["promedio"] = info["total"] / info["count"] if info["count"] else 0
        if info["promedio"] < mejor_promedio:
            mejor_promedio = info["promedio"]
            mejor_grupo = g

    return {"mejor_grupo": mejor_grupo, "grupos": grupos, "total_grupos": len(grupos)}


def _agrupar_insumos_texto(lineas: list[dict]) -> list[dict]:
    """Agrupación de respaldo por descripción normalizada (sin IA)."""
    grupos: dict = {}
    orden: list = []
    for idx, l in enumerate(lineas):
        clave = l["desc"].lower()
        if clave not in grupos:
            grupos[clave] = {"canonical": l["desc"], "unidad": l["unidad"], "tipo": l["tipo"], "indices": []}
            orden.append(clave)
        grupos[clave]["indices"].append(idx)
    return [grupos[k] for k in orden]


def subir_insumo_al_banco(datos: dict) -> dict:
    """Inserta un insumo suelto en el banco de APUs (columnas de ítem/proyecto vacías)."""
    descripcion = (datos.get("insumo_descripcion") or "").strip()
    if not descripcion:
        raise ValueError("La descripción del insumo es obligatoria")

    from src.infrastructure.database.repositories.apu_repository import insert_apus_batch

    def _txt(k):
        v = datos.get(k)
        return v.strip() if isinstance(v, str) and v.strip() else None

    fila = {
        # Insumo
        "insumo_descripcion": descripcion,
        "insumo_unidad": _txt("insumo_unidad"),
        "tipo_insumo": _txt("tipo_insumo"),
        "codigo_insumo": _txt("codigo_insumo"),
        "rendimiento_insumo": datos.get("rendimiento_insumo"),
        "precio_unitario_apu": datos.get("precio_unitario_apu"),
        "precio_parcial_apu": datos.get("precio_parcial_apu"),
        # Ítem / APU
        "item": _txt("item"),
        "items_descripcion": _txt("items_descripcion"),
        "item_unidad": _txt("item_unidad"),
        "precio_unitario": datos.get("precio_unitario"),
        # Proyecto / entidad
        "nombre_proyecto": _txt("nombre_proyecto"),
        "entidad": _txt("entidad"),
        "ciudad": _txt("ciudad"),
        "pais": _txt("pais"),
        "contratista": _txt("contratista"),
        "numero_contrato": _txt("numero_contrato"),
        "fecha_aprobacion_apu": _txt("fecha_aprobacion_apu"),
        "observacion": (datos.get("observacion") or "Insumo cargado manualmente al banco").strip(),
    }
    resultado = insert_apus_batch([fila])
    if resultado.get("status") != "success":
        raise RuntimeError("No se pudo insertar el insumo en el banco")
    creado = resultado.get("count", 0) > 0
    return {
        "success": True,
        "creado": creado,
        "mensaje": "Insumo agregado al banco de APUs." if creado else "El insumo ya existía en el banco (no se duplicó).",
    }


def _comparar_proveedores(insumos: list[dict]) -> dict:
    """Compara los proveedores (grupos) por precio total ofertado de sus insumos."""
    grupos: dict = {}
    for ins in insumos:
        g = ins.get("grupo_cotizacion", 1)
        if g not in grupos:
            grupos[g] = {"total": 0.0, "count": 0, "archivo": ins.get("nombre_archivo") or f"Cotización {g}"}
        precio_insumo = ins.get("precio_unitario_apu")
        if precio_insumo is None:
            precio_insumo = ins.get("precio_unitario")
        grupos[g]["total"] += float(precio_insumo or 0)
        grupos[g]["count"] += 1

    mejor_grupo = None
    mejor_total = float("inf")
    for g, info in grupos.items():
        info["promedio"] = info["total"] / info["count"] if info["count"] else 0
        if info["total"] < mejor_total:
            mejor_total = info["total"]
            mejor_grupo = g
    return {"mejor_grupo": mejor_grupo, "grupos": grupos, "total_grupos": len(grupos)}


def _generar_resumen_insumos(insumos_comparados: list, comparacion_grupos: dict) -> tuple:
    total = len(insumos_comparados)
    con_banco = sum(1 for i in insumos_comparados if i.get("existe_en_banco"))
    n_proveedores = comparacion_grupos.get("total_grupos", 0)
    mejor = comparacion_grupos.get("mejor_grupo")
    mejor_archivo = ""
    if mejor is not None:
        mejor_archivo = comparacion_grupos.get("grupos", {}).get(mejor, {}).get("archivo", f"Cotización {mejor}")
    resumen = (
        f"Comparación de {total} insumo(s) entre {n_proveedores} proveedor(es). "
        f"{con_banco} con referencia en el banco de APUs."
    )
    if mejor_archivo:
        resumen += f" Proveedor con menor precio total: {mejor_archivo}."
    return resumen, "revisar"
