"""
Application: Manage Análisis APU Use Case
Approval workflow orchestration: create, analyze, pre-approve, reject, approve.
"""

import json
import logging
from datetime import date, timedelta
from typing import Optional

from src.application.use_cases.notificaciones import notificar_transicion
from src.infrastructure.database.repositories.analisis_repository import (
    analisis_repo,
    _tokenizar,
    _similitud_tokens,
)
from src.infrastructure.ai.provider import ai_provider

log = logging.getLogger("mapus.application.analisis")

ESTADOS = [
    "pendiente_analisis",
    "analizado",
    "preaprobado",
    "rechazado",
    "nuevas_cotizaciones",
    "aprobado_subgerente",
    "aprobado_legal",
]


def _detectar_modo(insumos: list[dict]) -> str:
    """Adivina si la solicitud es un 'APU completo' (ítem + insumos con rendimiento)
    o 'solo insumos' (comparación de precios entre proveedores). El analista puede
    corregirlo luego con set_tipo_comparacion()."""
    if not insumos:
        return "apu"
    from collections import defaultdict
    por_item: dict = defaultdict(int)
    con_rendimiento = 0
    for ins in insumos:
        clave = (
            ins.get("grupo_cotizacion", 1),
            (ins.get("item") or "").strip(),
            (ins.get("items_descripcion") or "").strip(),
        )
        por_item[clave] += 1
        if ins.get("rendimiento_insumo") is not None:
            con_rendimiento += 1
    avg_insumos = len(insumos) / max(len(por_item), 1)
    frac_rendimiento = con_rendimiento / len(insumos)
    # Un APU tiene ítems descompuestos en varios insumos con rendimiento.
    return "apu" if (avg_insumos >= 2 and frac_rendimiento >= 0.3) else "insumos"


def crear_solicitud(grupos_insumos: list[dict], proyecto_id: Optional[int] = None) -> int:
    todos = []
    for grupo in grupos_insumos:
        gidx = grupo.get("grupo_cotizacion", 1)
        for ins in grupo.get("insumos", []):
            fila = dict(ins)
            fila.setdefault("grupo_cotizacion", gidx)
            todos.append(fila)
    tipo = _detectar_modo(todos)
    return analisis_repo.crear_solicitud(grupos_insumos, proyecto_id, tipo)


def set_tipo_comparacion(solicitud_id: int, tipo: str) -> dict:
    if tipo not in ("apu", "insumos"):
        raise ValueError("Tipo de comparación inválido (usa 'apu' o 'insumos')")
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError(f"Solicitud {solicitud_id} no encontrada")
    if solicitud.get("estado") == "aprobado_legal":
        raise ValueError("No se puede cambiar el modo de una solicitud ya firmada legalmente")
    analisis_repo.actualizar_tipo_comparacion(solicitud_id, tipo)
    etiqueta = "APU completo" if tipo == "apu" else "Solo insumos (proveedores)"
    return {"success": True, "tipo_comparacion": tipo, "mensaje": f"Modo actualizado a: {etiqueta}."}


def seleccionar_proyecto(solicitud_id: int, proyecto_id: int) -> dict:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError(f"Solicitud {solicitud_id} no encontrada")
    if solicitud.get("estado") == "aprobado_legal":
        raise ValueError("No se puede cambiar el proyecto de una solicitud ya firmada legalmente")
    if not analisis_repo.existe_proyecto(proyecto_id):
        raise ValueError(f"Proyecto {proyecto_id} no encontrado")

    analisis_repo.actualizar_proyecto_id(solicitud_id, proyecto_id)
    return {"success": True, "mensaje": f"Proyecto #{proyecto_id} asignado a la solicitud #{solicitud_id}."}


def get_solicitudes(estado: Optional[str] = None) -> list:
    return analisis_repo.get_solicitudes(estado)


def get_solicitud(solicitud_id: int) -> Optional[dict]:
    return analisis_repo.get_solicitud(solicitud_id)


def realizar_analisis(solicitud_id: int) -> dict:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError(f"Solicitud {solicitud_id} no encontrada")

    insumos = solicitud.get("insumos", [])
    if not insumos:
        raise ValueError("La solicitud no tiene insumos para analizar")

    # Determina el modo: si no está fijado, se auto-detecta y se persiste.
    tipo = solicitud.get("tipo_comparacion")
    if not tipo:
        tipo = _detectar_modo(insumos)
        analisis_repo.actualizar_tipo_comparacion(solicitud_id, tipo)

    if tipo == "insumos":
        # Modo 'solo insumos': se comparan precios entre proveedores (no se crea ítem en el proyecto).
        insumos_comparados = _analizar_insumos_proveedores(insumos)
        # La IA confirma cuáles referencias del banco son realmente el mismo insumo.
        insumos_comparados = _confirmar_referencias_ia(insumos_comparados)
        comparacion_grupos = _comparar_proveedores(insumos)
        resumen, recomendacion = _generar_resumen_insumos(insumos_comparados, comparacion_grupos)
        analisis_json = json.dumps({
            "modo": "insumos",
            "items": [],
            "insumos_comparados": insumos_comparados,
            "comparacion_grupos": comparacion_grupos,
        }, default=str)
        items_analizados = []
    else:
        # Modo 'APU completo': la unidad de análisis es el ítem con sus insumos.
        apus_cotizados = _agrupar_por_item(insumos)
        items_analizados = [_analizar_apu_con_banco(apu) for apu in apus_cotizados]
        comparacion_grupos = _comparar_cotizaciones(items_analizados)
        resumen, recomendacion = _generar_resumen_ia(apus_cotizados, items_analizados, comparacion_grupos)
        analisis_json = json.dumps({
            "modo": "apu",
            "items": items_analizados,
            "comparacion_grupos": comparacion_grupos,
        }, default=str)

    analisis_repo.guardar_analisis(solicitud_id, analisis_json, resumen, recomendacion)
    analisis_repo.actualizar_estado(solicitud_id, "analizado")

    proyecto_id = solicitud.get("proyecto_id")
    if proyecto_id:
        proyecto_info = f"proyecto #{proyecto_id} (seleccionado manualmente)"
    else:
        nombre_proyecto = solicitud.get("nombre_proyecto", "")
        proyecto_id = analisis_repo.resolver_proyecto_por_nombre(nombre_proyecto)
        if proyecto_id:
            analisis_repo.actualizar_proyecto_id(solicitud_id, proyecto_id)
            proyecto_info = f"proyecto #{proyecto_id}"
        else:
            proyecto_info = "proyecto no identificado — selecciónalo manualmente antes de la firma legal"

    notificar_transicion(solicitud_id, "analizado")

    return {
        "solicitud_id": solicitud_id,
        "items_analizados": items_analizados,
        "resumen": resumen,
        "recomendacion": recomendacion,
        "proyecto_asignado": proyecto_info,
    }


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


_TIPOS_INSUMO_VALIDOS = ["Materiales", "Equipos", "Mano de obra", "Transporte", "Herramienta", "Indirectos", "Otro"]


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


def _agrupar_insumos_ia(lineas: list[dict]) -> list[dict]:
    """Agrupa con IA las líneas de insumo que corresponden al MISMO insumo aunque los
    proveedores las describan distinto, y sugiere nombre canónico, unidad y tipo.
    Cae a agrupación por texto si la IA falla."""
    entrada = [
        {"i": idx, "desc": l["desc"], "und": l["unidad"], "proveedor": l["proveedor"]}
        for idx, l in enumerate(lineas)
    ]
    prompt = f"""Eres un experto en insumos de construcción civil.
Tienes líneas de insumo cotizadas por distintos proveedores. Agrupa las que corresponden al
MISMO insumo aunque estén descritas diferente (ej.: "cemento gris" y "cemento portland tipo I"
son el mismo insumo). Para cada grupo entrega un nombre canónico claro, la unidad y el tipo
(uno de: {", ".join(_TIPOS_INSUMO_VALIDOS)}).

LÍNEAS (usa el índice "i" para referirte a cada una):
{json.dumps(entrada, ensure_ascii=False)}

Responde SOLO con JSON válido:
{{"grupos": [{{"canonical": "nombre claro", "unidad": "und", "tipo": "Materiales", "indices": [0, 2]}}]}}
Cada índice debe aparecer en exactamente un grupo. NO incluyas texto adicional."""
    try:
        respuesta = ai_provider.generate_text(prompt, system="Eres un experto en insumos de construcción.", timeout=120)
        respuesta = respuesta.strip()
        if respuesta.startswith("```"):
            respuesta = respuesta.split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(respuesta)
        grupos = data.get("grupos", [])
        vistos: set = set()
        salida = []
        for g in grupos:
            indices = [i for i in g.get("indices", []) if isinstance(i, int) and 0 <= i < len(lineas) and i not in vistos]
            if not indices:
                continue
            vistos.update(indices)
            salida.append({
                "canonical": (g.get("canonical") or lineas[indices[0]]["desc"]).strip(),
                "unidad": (g.get("unidad") or lineas[indices[0]]["unidad"] or "").strip(),
                "tipo": (g.get("tipo") or lineas[indices[0]]["tipo"] or "").strip(),
                "indices": indices,
            })
        # Cualquier línea que la IA olvidó se agrega como su propio grupo.
        faltantes = [i for i in range(len(lineas)) if i not in vistos]
        for i in faltantes:
            salida.append({"canonical": lineas[i]["desc"], "unidad": lineas[i]["unidad"], "tipo": lineas[i]["tipo"], "indices": [i]})
        return salida or _agrupar_insumos_texto(lineas)
    except Exception as e:
        log.warning("Agrupación IA de insumos falló, se usa texto: %s", e)
        return _agrupar_insumos_texto(lineas)


def _analizar_insumos_proveedores(insumos: list[dict]) -> list[dict]:
    """Modo 'solo insumos': la IA agrupa el mismo insumo entre proveedores y se compara
    su precio, más una referencia del banco de APUs con proyecto y entidad. En este modo
    el precio del insumo viaja en `precio_unitario`."""
    lineas = []
    for ins in insumos:
        desc = (ins.get("insumo_descripcion") or ins.get("items_descripcion") or "").strip()
        if not desc:
            continue
        # Precio del INSUMO (no del ítem): si el archivo es un APU, el precio del
        # insumo viaja en precio_unitario_apu; si es una lista de insumos sueltos,
        # viaja en precio_unitario. Se toma el primero disponible.
        precio_insumo = ins.get("precio_unitario_apu")
        if precio_insumo is None:
            precio_insumo = ins.get("precio_unitario")
        lineas.append({
            "desc": desc,
            "unidad": (ins.get("insumo_unidad") or ins.get("item_unidad") or "").strip(),
            "codigo": (ins.get("codigo_insumo") or "").strip(),
            "tipo": ins.get("tipo_insumo") or "",
            "grupo": ins.get("grupo_cotizacion", 1),
            "proveedor": ins.get("nombre_archivo") or f"Cotización {ins.get('grupo_cotizacion', 1)}",
            "precio": float(precio_insumo or 0),
            "rendimiento": ins.get("rendimiento_insumo"),
            "precio_parcial": ins.get("precio_parcial_apu"),
        })
    if not lineas:
        return []

    clusters = _agrupar_insumos_ia(lineas)

    resultado = []
    for cl in clusters:
        miembros = [lineas[i] for i in cl["indices"]]
        proveedores = [
            {
                "grupo": m["grupo"], "proveedor": m["proveedor"], "precio": m["precio"],
                "rendimiento": m.get("rendimiento"), "precio_parcial": m.get("precio_parcial"),
            }
            for m in miembros
        ]
        precios = [p["precio"] for p in proveedores if p["precio"] > 0]
        mejor = min(precios) if precios else None
        for p in proveedores:
            p["es_menor"] = mejor is not None and p["precio"] == mejor and p["precio"] > 0

        # Busca con las descripciones ORIGINALES de los proveedores (no el nombre
        # canónico de la IA, que junta palabras: "minicargador"). Así la palabra
        # distintiva es real ("cargador", "retroexcavadora") y no un compuesto.
        textos = {m["desc"] for m in miembros if m.get("desc")}
        if not textos:
            textos = {cl["canonical"]}
        referencias = analisis_repo.buscar_insumos_similares(" ".join(textos), max_ref=12)
        for r in referencias:
            pb = float(r.get("precio_unitario_apu") or 0)
            r["diferencia"] = round(mejor - pb, 2) if (mejor is not None and pb) else None
            r["diferencia_pct"] = round((mejor - pb) / pb * 100, 1) if (mejor is not None and pb) else None

        codigo = next((m["codigo"] for m in miembros if m["codigo"]), "")
        tipo = cl.get("tipo") or next((m["tipo"] for m in miembros if m["tipo"]), "")
        unidad = cl.get("unidad") or next((m["unidad"] for m in miembros if m["unidad"]), "")
        resultado.append({
            "descripcion": cl["canonical"],
            "unidad": unidad,
            "codigo": codigo,
            "tipo_insumo": tipo,
            # Sugerencia editable para subir el insumo al banco:
            "sugerencia": {
                "insumo_descripcion": cl["canonical"],
                "insumo_unidad": unidad,
                "tipo_insumo": tipo,
                "codigo_insumo": codigo,
                "precio_unitario_apu": mejor,
            },
            "descripciones_originales": sorted({m["desc"] for m in miembros}),
            "proveedores": proveedores,
            "mejor_precio": mejor,
            "mejor_proveedor": next((p["proveedor"] for p in proveedores if p.get("es_menor")), None),
            "banco_referencia": referencias,
            "mejor_precio_banco": min(
                (float(r.get("precio_unitario_apu") or 0) for r in referencias if r.get("precio_unitario_apu")),
                default=None,
            ),
            "existe_en_banco": len(referencias) > 0,
        })
    return resultado


def _confirmar_referencias_ia(insumos_comparados: list[dict]) -> list[dict]:
    """La IA decide, sobre las DESCRIPCIONES DISTINTAS del banco, cuáles son realmente
    el mismo insumo (maneja las muchas variantes: escritura, espaciado, abreviaturas,
    sinónimos técnicos, capacidades/potencias). Una sola llamada; si la IA falla o no
    confirma nada, se conservan los resultados heurísticos (no destructivo)."""
    payload = []
    for i, ins in enumerate(insumos_comparados):
        refs = ins.get("banco_referencia") or []
        if not refs:
            continue
        # Descripciones DISTINTAS presentes en las referencias (no filas duplicadas).
        distintas = []
        vistas = set()
        for r in refs:
            d = (r.get("insumo_descripcion") or "").strip()
            if d and d.lower() not in vistas:
                vistas.add(d.lower())
                distintas.append(d)
        payload.append({"i": i, "insumo": ins.get("descripcion"), "unidad": ins.get("unidad"),
                        "opciones": [{"k": k, "desc": d} for k, d in enumerate(distintas)]})
        ins["_distintas"] = distintas
    if not payload:
        for ins in insumos_comparados:
            ins.pop("_distintas", None)
        return insumos_comparados

    prompt = f"""Eres un ingeniero experto en insumos de construcción civil (equipos, materiales,
mano de obra, transporte). Para cada INSUMO, mira las OPCIONES de descripción del banco y
elige SOLO las que se refieren REALMENTE al mismo insumo.

Criterios:
- Considera equivalentes las variantes de forma: mayúsculas/minúsculas, espaciado, tildes,
  abreviaturas, sinónimos técnicos y diferencias de marca o de capacidad/potencia menores
  (ej.: "minicargador" = "mini cargador" = "MINICARGADOR 40HP"; "retroexcavadora sobre oruga" =
  "retro excavadora oruga"; "cemento gris" = "cemento portland tipo I").
- DESCARTA lo que solo comparte una palabra genérica pero es otra cosa (ej.: para
  "Retroexcavadora sobre oruga" descarta "Martillo de hinca montado sobre oruga"; para
  "Carrotanque de agua" descarta "Agua" a secas).

INSUMOS Y OPCIONES (usa "i" del insumo y "k" de la opción):
{json.dumps(payload, ensure_ascii=False)}

Responde SOLO con JSON válido:
{{"resultados": [{{"i": 0, "validas": [0, 2]}}]}}
"validas" = índices k de las descripciones correctas (lista vacía si ninguna). Sin texto extra."""
    try:
        respuesta = ai_provider.generate_text(prompt, system="Eres un ingeniero experto en insumos de construcción.", timeout=120)
        respuesta = respuesta.strip()
        if respuesta.startswith("```"):
            respuesta = respuesta.split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(respuesta)
        mapa = {}
        for r in data.get("resultados", []):
            if isinstance(r.get("i"), int):
                mapa[r["i"]] = {k for k in r.get("validas", []) if isinstance(k, int)}
    except Exception as e:
        log.warning("Confirmación IA de referencias de insumos falló: %s", e)
        for ins in insumos_comparados:
            ins.pop("_distintas", None)
        return insumos_comparados

    for i, ins in enumerate(insumos_comparados):
        distintas = ins.pop("_distintas", None)
        refs = ins.get("banco_referencia") or []
        if not refs or distintas is None or i not in mapa:
            continue
        validas = mapa[i]
        if not validas:
            continue  # no destructivo: conservar heurísticos
        descs_ok = {distintas[k].lower() for k in validas if 0 <= k < len(distintas)}
        if not descs_ok:
            continue
        filtrados = [r for r in refs if (r.get("insumo_descripcion") or "").strip().lower() in descs_ok]
        if not filtrados:
            continue
        ins["banco_referencia"] = filtrados
        ins["existe_en_banco"] = True
        precios = [float(r["precio_unitario_apu"]) for r in filtrados if r.get("precio_unitario_apu")]
        ins["mejor_precio_banco"] = min(precios) if precios else None
    return insumos_comparados


def subir_insumo_al_banco(datos: dict) -> dict:
    """Inserta un insumo suelto en el banco de APUs (columnas de ítem/proyecto vacías)."""
    descripcion = (datos.get("insumo_descripcion") or "").strip()
    if not descripcion:
        raise ValueError("La descripción del insumo es obligatoria")

    from src.infrastructure.database.repositories.apu_repository import insert_apus_batch

    fila = {
        "insumo_descripcion": descripcion,
        "insumo_unidad": (datos.get("insumo_unidad") or "").strip() or None,
        "tipo_insumo": (datos.get("tipo_insumo") or "").strip() or None,
        "codigo_insumo": (datos.get("codigo_insumo") or "").strip() or None,
        "precio_unitario_apu": datos.get("precio_unitario_apu"),
        "observacion": (datos.get("observacion") or "Insumo cargado desde comparación de proveedores").strip(),
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


def _contexto_aprendizaje_rechazos(limit: int = 10) -> str:
    """Motivos de rechazos históricos para que la IA aplique criterios que los
    revisores humanos ya usaron. Devuelve cadena vacía si no hay datos."""
    try:
        rechazos = analisis_repo.get_aprendizaje_rechazos(limit)
    except Exception:
        log.exception("No se pudo consultar aprendizaje_rechazos")
        return ""
    if not rechazos:
        return ""
    lineas = "\n".join(
        f"- {r.get('motivo_rechazo', '')}" for r in rechazos if r.get("motivo_rechazo")
    )
    if not lineas:
        return ""
    return f"""
CRITERIOS APRENDIDOS DE RECHAZOS ANTERIORES (los revisores humanos rechazaron cotizaciones por estos motivos;
tenlos en cuenta al evaluar y menciona en observaciones si alguno aplica):
{lineas}
"""


def _resumen_insumos_para_ia(insumos: list, con_precio: bool) -> list:
    """Compacta la lista de insumos para el prompt (máx 25 líneas)."""
    salida = []
    for i in (insumos or [])[:25]:
        fila = {
            "tipo": i.get("tipo_insumo"),
            "desc": i.get("insumo_descripcion"),
            "und": i.get("insumo_unidad"),
            "rend": i.get("rendimiento_insumo"),
        }
        if con_precio and i.get("precio_unitario_apu") is not None:
            fila["precio"] = i.get("precio_unitario_apu")
        salida.append(fila)
    return salida


def _analisis_apu_con_ia(apu: dict, candidatos: list, resultado: dict) -> dict:
    tiene_banco = len(candidatos) > 0
    contexto_rechazos = _contexto_aprendizaje_rechazos()

    cotizado = {
        "item": apu.get("item"),
        "descripcion": apu.get("descripcion"),
        "unidad": apu.get("unidad"),
        "precio_ofertado": apu.get("precio_ofertado"),
        "insumos": _resumen_insumos_para_ia(apu.get("insumos"), con_precio=False),
    }
    banco = []
    for idx, c in enumerate(candidatos[:4]):
        banco.append({
            "indice": idx,
            "proyecto": c.get("nombre_proyecto"),
            "entidad": c.get("entidad"),
            "ciudad": c.get("ciudad"),
            "item": c.get("item"),
            "descripcion": c.get("items_descripcion"),
            "precio_unitario": c.get("precio_unitario"),
            "insumos": _resumen_insumos_para_ia(c.get("insumos"), con_precio=True),
        })
    prompt_banco = json.dumps(banco, default=str, ensure_ascii=False, indent=2) if tiene_banco \
        else "NO HAY APUs similares en el banco."

    prompt = f"""Eres un ingeniero civil experto en Análisis de Precios Unitarios (APU).

APU COTIZADO (a evaluar):
{json.dumps(cotizado, default=str, ensure_ascii=False, indent=2)}

APUs CANDIDATOS DEL BANCO (posibles equivalentes, con su proyecto y entidad):
{prompt_banco}
{contexto_rechazos}
INSTRUCCIONES:
- Determina qué candidato del banco corresponde al MISMO trabajo (por descripción e insumos), si alguno.
- Si hay un equivalente, compara la ESTRUCTURA de insumos (mismos tipos/materiales), los RENDIMIENTOS y los PRECIOS.
- Si NO hay equivalente en el banco, evalúa el precio del ítem con tu criterio profesional.

Responde SOLO con un JSON válido:
- mejor_candidato_indice: entero con el "indice" del candidato equivalente, o null si ninguno
- estructura_insumos_coincide: true/false (si hay equivalente; null si no)
- rendimiento_coincide: true/false (si hay equivalente; null si no)
- observaciones: string breve explicando la comparación (diferencias de precio/rendimiento relevantes)
- recomendacion: "aprobar" o "rechazar" o "revisar"

NO incluyas texto adicional, solo el JSON."""
    try:
        respuesta = ai_provider.generate_text(prompt, system="Eres un ingeniero civil experto en APUs.", timeout=120)
        respuesta = respuesta.strip()
        if respuesta.startswith("```"):
            respuesta = respuesta.split("\n", 1)[-1]
            respuesta = respuesta.rsplit("```", 1)[0]
        analisis = json.loads(respuesta)
        resultado["estructura_insumos_coincide"] = analisis.get("estructura_insumos_coincide")
        resultado["rendimiento_coincide"] = analisis.get("rendimiento_coincide")
        if analisis.get("observaciones"):
            resultado["observaciones"] = analisis["observaciones"]
        resultado["recomendacion"] = analisis.get("recomendacion", "revisar")
        idx = analisis.get("mejor_candidato_indice")
        if isinstance(idx, int) and 0 <= idx < len(resultado["candidatos"]):
            resultado["candidatos"][idx]["es_match_ia"] = True
            # Si la IA confirma un equivalente, ese pasa a ser la referencia.
            for c in resultado["candidatos"]:
                c["es_referencia"] = False
            resultado["candidatos"][idx]["es_referencia"] = True
            _fijar_referencia(resultado, resultado["candidatos"][idx], resultado.get("precio_ofertado") or 0)
    except Exception as e:
        log.exception("Error en análisis IA para APU %s: %s", apu.get("item"), e)
        resultado["observaciones"] = "No se pudo completar el análisis automático"
        resultado["recomendacion"] = "revisar"

    return resultado


def _generar_resumen_ia(apus_cotizados: list, items_analizados: list, comparacion_grupos: dict = None) -> tuple:
    total_items = len(items_analizados)
    recomendaciones = [i.get("recomendacion", "") for i in items_analizados]
    aprobar = sum(1 for r in recomendaciones if r == "aprobar")
    rechazar = sum(1 for r in recomendaciones if r == "rechazar")
    revisar = sum(1 for r in recomendaciones if r == "revisar")
    items_con_banco = sum(1 for i in items_analizados if i.get("existe_en_banco"))
    items_sin_banco = total_items - items_con_banco

    grupo_info = ""
    if comparacion_grupos and comparacion_grupos.get("total_grupos", 0) > 1:
        grupos = comparacion_grupos.get("grupos", {})
        mejor = comparacion_grupos.get("mejor_grupo")
        grupo_info = "\nCOMPARACIÓN ENTRE COTIZACIONES:\n"
        for g, info in grupos.items():
            marca = " ← MEJOR OPCIÓN" if g == mejor else ""
            grupo_info += f"Cotización {g} ({info.get('archivo', '')}): ${info.get('total', 0):,.0f} total, ${info.get('promedio', 0):,.0f} promedio/ítem{marca}\n"
        grupo_info += f"\nLa cotización con mejor relación precio es: Cotización {mejor}\n"

    prompt = f"""Eres un ingeniero civil experto en APUs.
Genera un resumen ejecutivo del siguiente análisis de cotizaciones APU.

Total de ítems analizados: {total_items}
Aprobados por IA: {aprobar}
Rechazados por IA: {rechazar}
Para revisión manual: {revisar}
Ítems con datos en banco de APUs: {items_con_banco}
Ítems SIN datos en banco de APUs: {items_sin_banco}
{grupo_info}

Detalle del análisis:
{json.dumps([
    {
        "item": i.get("item"),
        "descripcion": i.get("descripcion"),
        "precio_ofertado": i.get("precio_ofertado"),
        "mejor_precio_banco": i.get("mejor_precio_banco"),
        "diferencia_precio": i.get("diferencia_precio"),
        "existe_en_banco": i.get("existe_en_banco"),
        "recomendacion": i.get("recomendacion"),
        "observaciones": i.get("observaciones"),
    }
    for i in items_analizados
], default=str, indent=2)}

Responde SOLO con un JSON:
{{"resumen": "texto del resumen", "recomendacion": "aprobar|rechazar|revisar"}}"""
    try:
        respuesta = ai_provider.generate_text(prompt, system="Eres un ingeniero civil experto en APUs.", timeout=120)
        import re
        text = respuesta.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0].strip()
        try:
            resultado = json.loads(text)
        except json.JSONDecodeError:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                resultado = json.loads(text[brace_start:brace_end + 1])
            else:
                raise
        if resultado.get("resumen") and resultado.get("recomendacion"):
            return resultado["resumen"], resultado["recomendacion"]
    except Exception as e:
        log.warning("Error generando resumen IA: %s", e)

    return f"Se analizaron {total_items} ítems ({items_con_banco} con datos en banco, {items_sin_banco} sin datos). {aprobar} aprobados, {rechazar} rechazados, {revisar} en revisión.", "revisar"


def preaprobar(solicitud_id: int, usuario_rol: str, usuario_nombre: str) -> dict:
    from src.infrastructure.database.connection import get_db_connection
    conn = get_db_connection()
    try:
        if not analisis_repo.actualizar_estado(solicitud_id, "preaprobado", "AND estado = 'analizado'", conn=conn):
            raise ValueError("La solicitud no está en estado 'analizado'")
        analisis_repo.insertar_historial(solicitud_id, "preaprobado", usuario_rol, usuario_nombre, conn=conn)
        analisis_repo.insertar_historial(solicitud_id, "pendiente_aprobacion_subgerente", usuario_rol, usuario_nombre, conn=conn)
        conn.commit()
        notificar_transicion(solicitud_id, "preaprobado", usuario_nombre)
        return {"success": True, "mensaje": "APU preaprobado. Enviado a subgerente técnico."}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rechazar(solicitud_id: int, usuario_rol: str, usuario_nombre: str, motivo: str) -> dict:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError("Solicitud no encontrada")
    estado_actual = solicitud.get("estado")
    if estado_actual not in ("analizado", "nuevas_cotizaciones"):
        raise ValueError(f"No se puede rechazar en estado '{estado_actual}'")

    from src.infrastructure.database.connection import get_db_connection
    conn = get_db_connection()
    try:
        fecha_limite = date.today() + timedelta(days=5)
        analisis_repo.actualizar_estado(solicitud_id, "nuevas_cotizaciones", conn=conn)
        analisis_repo.insertar_historial(solicitud_id, "rechazado", usuario_rol, usuario_nombre, motivo, conn=conn)

        analisis = solicitud.get("analisis", {})
        if analisis and analisis.get("id"):
            analisis_repo.insertar_aprendizaje(analisis["id"], motivo, f"Rechazado por {usuario_rol}: {usuario_nombre}", conn=conn)

        conn.commit()
        notificar_transicion(solicitud_id, "nuevas_cotizaciones", usuario_nombre)
        return {"success": True, "mensaje": f"APU rechazado. Se solicitarán nuevas cotizaciones (límite: {fecha_limite}).", "fecha_limite": str(fecha_limite)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def nuevas_cotizaciones_recibidas(solicitud_id: int) -> dict:
    fecha_limite = date.today() + timedelta(days=3)
    if not analisis_repo.actualizar_estado(solicitud_id, "analizado"):
        raise ValueError("No se pudo actualizar el estado")
    analisis_repo.insertar_historial(solicitud_id, "nuevas_cotizaciones_recibidas", "contraparte", "Contraparte")
    notificar_transicion(solicitud_id, "nuevas_cotizaciones_recibidas")
    return {"success": True, "mensaje": f"Nuevas cotizaciones registradas. Plazo para aprobar: {fecha_limite}."}


def aprobar_subgerente(solicitud_id: int, usuario_rol: str, usuario_nombre: str) -> dict:
    from src.infrastructure.database.connection import get_db_connection
    conn = get_db_connection()
    try:
        if not analisis_repo.actualizar_estado(solicitud_id, "aprobado_subgerente", "AND estado = 'preaprobado'", conn=conn):
            raise ValueError("La solicitud no está en estado 'preaprobado'")
        analisis_repo.insertar_historial(solicitud_id, "aprobado_subgerente", usuario_rol, usuario_nombre, conn=conn)
        analisis_repo.insertar_historial(solicitud_id, "pendiente_firma_legal", "sistema", "Sistema", conn=conn)
        conn.commit()
        notificar_transicion(solicitud_id, "aprobado_subgerente", usuario_nombre)
        return {"success": True, "mensaje": "Aprobado por subgerente técnico. Enviado para firma legal."}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def firmar_legal(solicitud_id: int, usuario_rol: str, usuario_nombre: str) -> dict:
    from src.infrastructure.database.connection import get_db_connection
    conn = get_db_connection()
    try:
        if not analisis_repo.actualizar_estado(solicitud_id, "aprobado_legal", "AND estado = 'aprobado_subgerente'", conn=conn):
            raise ValueError("La solicitud no está en estado 'aprobado_subgerente'")
        analisis_repo.insertar_historial(solicitud_id, "aprobado_legal", usuario_rol, usuario_nombre, conn=conn)

        items_creados = _crear_items_presupuesto(solicitud_id, conn)

        conn.commit()
        notificar_transicion(solicitud_id, "aprobado_legal", usuario_nombre)
        msg = "APU aprobado y firmado legalmente. Incorporado al banco de APUs."
        if items_creados:
            msg += f" {items_creados} ítem(s) enviado(s) al presupuesto del proyecto."
        return {"success": True, "mensaje": msg, "items_creados": items_creados}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _crear_items_presupuesto(solicitud_id: int, conn) -> int:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        return 0

    # Modo 'solo insumos': es una comparación de precios entre proveedores, NO un APU.
    # No se incorpora nada al presupuesto (al proyecto solo se agregan ítems con su APU).
    if (solicitud.get("tipo_comparacion") or "apu") == "insumos":
        log.info("Solicitud %d en modo 'insumos' — no se crean ítems en el proyecto", solicitud_id)
        return 0

    analisis_data = solicitud.get("analisis") or {}
    items_analizados = analisis_data.get("items_analizados") or []

    proyecto_id = solicitud.get("proyecto_id")
    if not proyecto_id:
        log.warning("Solicitud %d sin proyecto_id — no se crearon items en presupuesto", solicitud_id)
        return 0

    creados = 0
    items_vistos = set()
    for item in items_analizados:
        codigo = (item.get("item") or "").strip()
        descripcion = (item.get("descripcion") or "").strip()
        if not codigo or not descripcion:
            continue
        if codigo in items_vistos:
            continue
        items_vistos.add(codigo)
        unidad = (item.get("unidad") or "").strip()
        precio = float(item.get("precio_ofertado") or 0)
        try:
            analisis_repo.crear_item_proyecto(
                solicitud_id, proyecto_id, codigo, descripcion,
                unidad, precio, conn=conn,
            )
            creados += 1
        except Exception:
            log.exception("Error creando item_proyecto para %s", codigo)
    return creados


def get_aprendizaje_rechazos(limit: int = 20) -> list:
    return analisis_repo.get_aprendizaje_rechazos(limit)


def eliminar_solicitud(solicitud_id: int) -> dict:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError(f"Solicitud {solicitud_id} no encontrada")
    if solicitud.get("estado") in ("aprobado_legal",):
        raise ValueError("No se puede eliminar una solicitud ya firmada legalmente")
    analisis_repo.eliminar_solicitud(solicitud_id)
    return {"success": True, "mensaje": f"Solicitud #{solicitud_id} eliminada correctamente."}
