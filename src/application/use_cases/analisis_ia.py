"""
Application: Análisis APU — ayudantes de IA.

Agrupación inteligente de insumos, confirmación de referencias del banco,
evaluación de APUs contra candidatos y resúmenes ejecutivos generados con IA.
"""

import json
import logging

from src.application.use_cases.analisis_comparacion import (
    _agrupar_insumos_texto,
    _fijar_referencia,
)
from src.infrastructure.database.repositories.analisis_repository import analisis_repo
from src.infrastructure.ai.provider import ai_provider

log = logging.getLogger("mapus.application.analisis_ia")

_TIPOS_INSUMO_VALIDOS = ["Materiales", "Equipos", "Mano de obra", "Transporte", "Herramienta", "Indirectos", "Otro"]


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
