import json
import re
import logging

from apu_extractor.ai_provider import generate_text as ai_generate

log = logging.getLogger("mapus.analisis.ai")


def parse_ia_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidate = text[brace_start:brace_end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            text = candidate

    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(r"(?<=\{|,)\s*(\w[\w\s]*?)\s*(?=:)", r'"\1"', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    resumen = re.search(r'"resumen"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    rec = re.search(r'"recomendacion"\s*:\s*"(aprobar|rechazar|revisar)"', text)
    result = {}
    if resumen:
        result["resumen"] = resumen.group(1)
    if rec:
        result["recomendacion"] = rec.group(1)
    return result


def analisis_con_ia(insumo: dict, banco_records: list, resultado: dict) -> dict:
    tiene_banco = len(banco_records) > 0
    prompt_banco = json.dumps(banco_records, default=str, indent=2) if tiene_banco else "NO HAY registros similares en el banco de APUs."

    prompt = f"""Eres un ingeniero civil experto en Análisis de Precios Unitarios (APU).

ÍTEM COTIZADO:
- Código: {insumo.get('item', 'N/A')}
- Descripción: {insumo.get('items_descripcion', 'N/A')}
- Unidad: {insumo.get('item_unidad', 'N/A')}
- Precio Unitario: ${insumo.get('precio_unitario', 'N/A')}
- Código Insumo: {insumo.get('codigo_insumo', 'N/A')}
- Descripción Insumo: {insumo.get('insumo_descripcion', 'N/A')}
- Unidad Insumo: {insumo.get('insumo_unidad', 'N/A')}
- Rendimiento: {insumo.get('rendimiento_insumo', 'N/A')}
- Tipo Insumo: {insumo.get('tipo_insumo', 'N/A')}

DATOS DEL BANCO DE APUs:
{prompt_banco}

INSTRUCCIONES:
- Si HAY datos en el banco, compáralos (estructura de insumos, rendimientos, precios).
- Si NO HAY datos similares en el banco, evalúa el precio del ítem según tu criterio profesional como ingeniero civil. Considera si el precio es razonable para el tipo de obra y la descripción.

Analiza y responde SOLO con un JSON válido con estos campos:
- estructura_insumos_coincide: true/false (si hay banco y el tipo de insumos es similar; si no hay banco, null)
- rendimiento_coincide: true/false (si hay banco y el rendimiento es similar ±20%; si no hay banco, null)
- observaciones: string con explicación breve del análisis indicando si hay o no datos en el banco
- recomendacion: "aprobar" o "rechazar" o "revisar"

NO incluyas texto adicional, solo el JSON."""
    try:
        respuesta = ai_generate(prompt, system="Eres un ingeniero civil experto en APUs.", timeout=120)
        respuesta = respuesta.strip()
        if respuesta.startswith("```"):
            respuesta = respuesta.split("\n", 1)[-1]
            respuesta = respuesta.rsplit("```", 1)[0]
        analisis = json.loads(respuesta)
        resultado["estructura_insumos_coincide"] = analisis.get("estructura_insumos_coincide") if tiene_banco else (analisis.get("estructura_insumos_coincide") if analisis.get("estructura_insumos_coincide") is not None else None)
        resultado["rendimiento_coincide"] = analisis.get("rendimiento_coincide") if tiene_banco else (analisis.get("rendimiento_coincide") if analisis.get("rendimiento_coincide") is not None else None)
        if analisis.get("observaciones"):
            resultado["observaciones"] = analisis["observaciones"]
        resultado["recomendacion"] = analisis.get("recomendacion", "revisar")
    except Exception as e:
        log.exception("Error en análisis IA para ítem %s: %s", insumo.get("item"), e)
        resultado["observaciones"] = "No se pudo completar el análisis automático"
        resultado["recomendacion"] = "revisar"

    return resultado


def generar_resumen_ia(insumos: list, items_analizados: list, comparacion_grupos: dict = None) -> tuple:
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
{json.dumps(items_analizados, default=str, indent=2)}

INSTRUCCIONES:
1. Si hay ítems SIN datos en el banco, menciónalo y explica que la recomendación se basa en el criterio profesional y la comparación entre cotizaciones recibidas.
2. Si hay múltiples cotizaciones (grupos), menciona cuál es la mejor opción basada en precios.
3. Proporciona un resumen breve (máximo 3 párrafos) del análisis general.
4. Da una recomendación global: "aprobar", "rechazar", o "revisar".

Responde SOLO con un JSON:
{{"resumen": "texto del resumen", "recomendacion": "aprobar|rechazar|revisar"}}

NO incluyas texto adicional, solo el JSON."""
    try:
        respuesta = ai_generate(prompt, system="Eres un ingeniero civil experto en APUs.", timeout=120)
        resultado = parse_ia_json(respuesta)
        if resultado.get("resumen") and resultado.get("recomendacion"):
            return resultado["resumen"], resultado["recomendacion"]
        log.warning("IA response missing fields, raw: %s", respuesta[:500])
    except Exception as e:
        log.warning("Error generando resumen IA: %s", e)
    return f"Se analizaron {total_items} ítems ({items_con_banco} con datos en banco, {items_sin_banco} sin datos). {aprobar} aprobados, {rechazar} rechazados, {revisar} en revisión.", \
           "revisar"
