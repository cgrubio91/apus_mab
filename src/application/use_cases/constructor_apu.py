"""
Application: Constructor de APU Use Case

Flujo liderado por el residente técnico:
  1. Crea un borrador describiendo la actividad/ítem y su ubicación.
  2. La IA propone la ESTRUCTURA del APU (insumos, rendimientos y precios
     sugeridos tomados del banco, priorizando referencias recientes y de la
     misma ciudad) y puede hacer preguntas para refinarla.
  3. El contratista registra los precios actualizados según sus cotizaciones.
  4. Se envía a análisis: se compara contra el banco (estructura + rendimientos)
     y continúa el flujo normal de aprobación.
"""

import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from src.application.use_cases.manage_analisis import realizar_analisis
from src.application.use_cases.notificaciones import crear_notificacion
from src.application.use_cases.ingesta_referencias import consultar_referencias
from src.domain.entities.referencia_externa import ReferenciaExterna
from src.infrastructure.ai.provider import ai_provider
from src.infrastructure.database.repositories.analisis_repository import (
    analisis_repo,
    _tokenizar,
    _similitud_tokens,
)
from src.infrastructure.database.repositories.referencia_externa_repository import referencia_externa_repo
from src.infrastructure.scraping.cype_source import CypeSource
from src.infrastructure.scraping.catalogo_materiales import CatalogoMaterialesSource
from src.application.use_cases.extract_city import extraer_ciudad_texto

log = logging.getLogger("mapus.application.constructor")

TIPOS_INSUMO_VALIDOS = ["Materiales", "Equipos", "Mano de obra", "Transporte", "Herramienta", "Indirectos", "Otro"]

# Ventanas de vigencia para preferir referencias del banco (días).
RECENCIA_EXCELENTE_DIAS = 180      # ≤ 6 meses
RECENCIA_BUENA_DIAS = 365          # ≤ 12 meses
RECENCIA_ACEPTABLE_DIAS = 730      # ≤ 24 meses


# ──────────────────────────────────────────────────────────────────
# Helper: Relleno automático de precios y rendimientos vía Webscraping en vivo
# ──────────────────────────────────────────────────────────────────

def _rellenar_precios_reales(propuesta: dict, ciudad: Optional[str] = None) -> dict:
    """Rellena precios nulos o 'sin ref' consultando en tiempo real CYPE Colombia,
    el catálogo de materiales comerciales (Homecenter) y el banco de referencias.
    
    Persiste en la BD las referencias externas encontradas para acelerar consultas futuras.
    """
    insumos = propuesta.get("insumos", [])
    if not insumos:
        return propuesta

    cype = CypeSource()
    catalogo = CatalogoMaterialesSource()
    nuevas_referencias = []
    notas_agregadas = []

    for ins in insumos:
        precio_actual = ins.get("precio")
        fuente_actual = ins.get("fuente") or ""
        
        # Si ya tiene un precio válido asignado por el banco (no 'sin ref'), continuar
        if precio_actual is not None and "sin ref" not in fuente_actual.lower() and "sin referencia" not in fuente_actual.lower():
            continue

        desc = (ins.get("descripcion") or "").strip()
        tipo = (ins.get("tipo_insumo") or "").strip()
        if not desc:
            continue

        precio_encontrado = None
        fuente_encontrada = None
        unidad_encontrada = None

        # 1. Intentar con CYPE Colombia (mano de obra oficial/ayudante, concreto, acero, madera, equipos)
        try:
            ref_cype = cype.buscar_referencia_insumo(desc, tipo_insumo=tipo)
            if ref_cype and ref_cype.get("precio") is not None:
                precio_encontrado = float(ref_cype["precio"])
                fuente_encontrada = ref_cype["fuente"]
                unidad_encontrada = ref_cype.get("unidad")
        except Exception as e:
            log.warning("Fallo consulta CYPE para '%s': %s", desc, e)

        # 2. Si no se encontró y es material, consultar catálogo comercial Homecenter / Constructor
        if precio_encontrado is None and tipo.lower() in ("materiales", "material", "otro"):
            try:
                termino = re.sub(r'\(.*?\)', '', desc).strip()
                tokens = [t for t in termino.split() if len(t) > 2]
                query_hc = " ".join(tokens[:3]) if tokens else termino
                prods = catalogo.buscar_material(query_hc, limite=1)
                if prods and prods[0].get("precio") is not None:
                    precio_encontrado = float(prods[0]["precio"])
                    fuente_encontrada = f"Constructor · {prods[0].get('nombre', 'Material')[:40]}"
                    unidad_encontrada = prods[0].get("unidad")
            except Exception as e:
                log.warning("Fallo consulta catálogo materiales para '%s': %s", desc, e)

        # 3. Si aún no hay precio, consultar la tabla de referencias externas acumuladas
        if precio_encontrado is None:
            try:
                refs_db = consultar_referencias(desc, limite=1)
                if refs_db and refs_db[0].get("precio") is not None:
                    precio_encontrado = float(refs_db[0]["precio"])
                    fuente_encontrada = f"{refs_db[0].get('fuente', 'Externa')} · {refs_db[0].get('descripcion', '')[:30]}"
            except Exception as e:
                log.warning("Fallo consulta referencias_externas DB para '%s': %s", desc, e)

        # Si se halló precio, asignarlo a la propuesta
        if precio_encontrado is not None:
            ins["precio"] = precio_encontrado
            ins["fuente"] = fuente_encontrada or "Mercado Colombia"
            if unidad_encontrada and ins.get("unidad") in (None, "", "und", "por definir"):
                ins["unidad"] = unidad_encontrada

            # Preparar para persistir en la tabla de referencias
            try:
                f_nombre = fuente_encontrada.split("·")[0].strip() if "·" in (fuente_encontrada or "") else "CYPE Colombia"
                nuevas_referencias.append(ReferenciaExterna(
                    fuente=f_nombre,
                    fuente_id=desc[:50],
                    granularidad="insumo",
                    descripcion=desc,
                    unidad=ins.get("unidad"),
                    precio=Decimal(str(precio_encontrado)),
                    rendimiento=Decimal(str(ins.get("rendimiento"))) if ins.get("rendimiento") is not None else None,
                    ciudad=ciudad,
                    fecha=date.today(),
                    observacion="Auto-cotizado por scraper en tiempo real",
                ))
            except Exception:
                pass
        else:
            notas_agregadas.append(f"• '{desc[:35]}': sin referencia de precio disponible")

    # Persistir en BD de forma segura
    if nuevas_referencias:
        try:
            referencia_externa_repo.upsert_muchas(nuevas_referencias)
        except Exception as e:
            log.warning("No se pudieron guardar referencias externas: %s", e)

    # Actualizar notas de la propuesta
    propuesta_actual = dict(propuesta)
    notas_existentes = propuesta_actual.get("notas", "")
    if notas_agregadas:
        nota_cype = "\nInsumos cotizados con scraper en tiempo real (CYPE Colombia / Mercado):\n" + "\n".join(notas_agregadas)
        propuesta_actual["notas"] = (notas_existentes + nota_cype) if notas_existentes else nota_cype

    return propuesta_actual



# ──────────────────────────────────────────────────────────────────
# Helpers puros (testeados sin BD)
# ──────────────────────────────────────────────────────────────────

def _parse_fecha(valor) -> Optional[date]:
    """Convierte fecha de la BD (date/datetime/str/None) a date."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _puntaje_recencia(fecha, hoy: Optional[date] = None) -> tuple[float, str]:
    """Puntaje y etiqueta según antigüedad de la referencia del banco."""
    hoy = hoy or date.today()
    f = _parse_fecha(fecha)
    if not f:
        return 0.15, "sin fecha"
    dias = (hoy - f).days
    if dias <= RECENCIA_EXCELENTE_DIAS:
        return 1.0, "≤ 6 meses"
    if dias <= RECENCIA_BUENA_DIAS:
        return 0.7, "≤ 12 meses"
    if dias <= RECENCIA_ACEPTABLE_DIAS:
        return 0.4, "≤ 24 meses"
    return 0.15, "desactualizada"


def _rankear_referencias(referencias: list[dict], ciudad: Optional[str] = None,
                         hoy: Optional[date] = None) -> list[dict]:
    """Ordena referencias del banco por: similitud del ítem, coincidencia de
    ciudad, recencia del precio y completitud. Agrega claves de apoyo para UI/IA."""
    ciudad_norm = (ciudad or "").strip().lower()
    rankeadas = []
    for r in (referencias or []):
        r = dict(r)
        rec_score, rec_etiqueta = _puntaje_recencia(r.get("fecha") or r.get("fecha_aprobacion_apu"), hoy)
        ciudad_coincide = bool(ciudad_norm) and (r.get("ciudad") or "").strip().lower() == ciudad_norm
        r["recencia"] = rec_etiqueta
        r["ciudad_coincide"] = ciudad_coincide
        r["_score"] = (
            float(r.get("similitud") or 0) * 3.0
            + (1.5 if ciudad_coincide else 0.0)
            + rec_score
            + int(bool(r.get("tiene_valor"))) * 0.5
        )
        rankeadas.append(r)
    rankeadas.sort(key=lambda r: r["_score"], reverse=True)
    return rankeadas


def _emparejar_filas_cotizacion(filas: list[dict], insumos_borrador: list[dict],
                                umbral: float = 0.45) -> tuple[list[dict], list[dict]]:
    """Empareja filas extraídas de una cotización del contratista con los insumos
    del borrador por similitud de descripción (greedy, cada lado se usa una vez).

    Devuelve (asignadas, sin_coincidencia). Cada asignada lleva `insumo_id`,
    `precio` y `similitud`."""
    pares: list[tuple[float, int, int]] = []
    for i_fila, fila in enumerate(filas):
        tokens_fila = _tokenizar(fila.get("insumo_descripcion") or "")
        if not tokens_fila:
            continue
        for i_ins, ins in enumerate(insumos_borrador):
            tokens_ins = _tokenizar(ins.get("insumo_descripcion") or "")
            sim = _similitud_tokens(tokens_fila, tokens_ins)
            if sim >= umbral:
                pares.append((sim, i_fila, i_ins))
    pares.sort(key=lambda p: (-p[0], p[1], p[2]))

    filas_usadas: set[int] = set()
    insumos_usados: set[int] = set()
    asignadas: list[dict] = []

    def _precio_de(fila: dict) -> Optional[float]:
        for k in ("precio_unitario_apu", "precio_unitario"):
            v = fila.get(k)
            try:
                v = float(v)
                if v > 0:
                    return v
            except (TypeError, ValueError):
                continue
        return None

    for sim, i_fila, i_ins in pares:
        if i_fila in filas_usadas or i_ins in insumos_usados:
            continue
        precio = _precio_de(filas[i_fila])
        if precio is None:
            continue
        filas_usadas.add(i_fila)
        insumos_usados.add(i_ins)
        asignadas.append({
            "insumo_id": insumos_borrador[i_ins].get("id"),
            "insumo_descripcion": insumos_borrador[i_ins].get("insumo_descripcion"),
            "descripcion_cotizacion": filas[i_fila].get("insumo_descripcion"),
            "precio": precio,
            "rendimiento_cotizado": filas[i_fila].get("rendimiento_insumo"),
            "similitud": round(sim, 3),
        })

    sin_coincidencia = [
        f for i, f in enumerate(filas)
        if i not in filas_usadas and _precio_de(f) is not None
    ]
    return asignadas, sin_coincidencia


def _extraer_json_ia(respuesta: str) -> dict:
    texto = respuesta.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[-1]
        texto = texto.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(texto)
    except json.JSONDecodeError:
        inicio, fin = texto.find("{"), texto.rfind("}")
        if inicio == -1 or fin <= inicio:
            raise
        data = json.loads(texto[inicio:fin + 1])
    if not isinstance(data, dict):
        raise ValueError("La IA no devolvió un objeto JSON")
    return data


# ──────────────────────────────────────────────────────────────────
# Propuesta IA
# ──────────────────────────────────────────────────────────────────

def _compactar_referencias_para_ia(refs_ranked: list[dict], max_refs: int = 4,
                                   max_insumos_por_ref: int = 20) -> list[dict]:
    salida = []
    for r in refs_ranked[:max_refs]:
        insumos = []
        for ins in (r.get("insumos") or [])[:max_insumos_por_ref]:
            precio = ins.get("precio_unitario_apu")
            insumos.append({
                "tipo": ins.get("tipo_insumo"),
                "desc": ins.get("insumo_descripcion"),
                "und": ins.get("insumo_unidad"),
                "rend": ins.get("rendimiento_insumo"),
                "precio": float(precio) if precio else None,
            })
        salida.append({
            "item": r.get("item"),
            "descripcion": r.get("items_descripcion"),
            "unidad": r.get("item_unidad"),
            "precio_unitario": float(r["precio_unitario"]) if r.get("precio_unitario") else None,
            "proyecto": r.get("nombre_proyecto"),
            "entidad": r.get("entidad"),
            "ciudad": r.get("ciudad"),
            "fecha": str(r.get("fecha")) if r.get("fecha") else None,
            "recencia": r.get("recencia"),
            "insumos": insumos,
        })
    return salida


_PROMPT_SISTEMA = "Eres un ingeniero civil experto en Análisis de Precios Unitarios (APU) de obra civil en Colombia."


def _construir_propuesta(solicitud: dict, refs_ranked: list[dict],
                         conversacion: Optional[list[dict]] = None) -> dict:
    """Llama a la IA para proponer la estructura del APU. Devuelve el JSON de la
    propuesta (insumos + preguntas) junto con las referencias usadas."""
    descripcion = solicitud.get("descripcion_actividad") or ""
    ciudad = solicitud.get("ciudad")
    contexto_conversacion = ""
    if conversacion:
        lineas = [f"- {m.get('rol', 'usuario')}: {m.get('texto', '')}" for m in conversacion[-12:]]
        contexto_conversacion = (
            "\nCONVERSACIÓN PREVIA (respuestas del residente a tus preguntas):\n" + "\n".join(lineas)
        )

    prompt = f"""Un residente de interventoría debe construir el APU de un ítem NO PREVISTO y quiere una
propuesta de estructura basada en el banco histórico de APUs.

ACTIVIDAD A ANALIZAR: "{descripcion}"
UNIDAD DEL ÍTEM: {solicitud.get('unidad_actividad') or 'por definir'}
CIUDAD/ZONA DE LA OBRA: {ciudad or 'no indicada'}
{contexto_conversacion}

REFERENCIAS DISPONIBLES (ordenadas por relevancia: similitud, cercanía a la ciudad y recencia;
el campo "recencia" indica qué tan viejo está el dato). Incluye referencias del banco interno
y externas (SECOP II). Se combinaron y reordenaron por relevancia para el ítem consultado:
{json.dumps(_compactar_referencias_para_ia(refs_ranked), default=str, ensure_ascii=False, indent=2)}

INSTRUCCIONES:
1. Propón la ESTRUCTURA completa del APU para esta actividad: lista de insumos por tipo
   ({", ".join(TIPOS_INSUMO_VALIDOS)}), con unidad, RENDIMIENTO (usa 1 cuando el insumo entra por cantidad
   directa, ej. materiales medidos en m³) y PRECIO UNITARIO.
2. Los PRECIOS y rendimientos deben salir de las REFERENCIAS disponibles (banco interno o SECOP II):
   - PRIMERO: intente usar las referencias del banco interno (las primeras de la lista).
   - SI NO HAY DATOS COMPARABLES para este tipo de insumo (ej. pintura bicomponente en frío,
     aplicación por spray, microesferas para retrorreflectividad):
     → Use referencias SECOP II como alternativa de mercado público colombiano.
   - En "fuente" indique claramente el origen:
     • Si usó datos del banco: "Banco: <proyecto> · <ciudad> · <fecha>"
     • Si usó datos SECOP II: "SECOP II · Contrato <número> · <ciudad> · <fecha>"
3. Si no hay referencia para un insumo indispensable, inclúyalo con precio null y explícalo en "notas".
4. Si falta información clave que cambie la estructura o los rendimientos (diámetros, profundidades,
   distancias de transporte, condiciones del terreno, condiciones de aplicación como temperatura,
   tiempo de curado, método spray vs rodillo), hágalo en "preguntas" (máximo 3, concretas).
5. Ajuste la propuesta según la CONVERSACIÓN PREVIA si existe.
3. Si no hay referencia para un insumo indispensable, inclúyelo con precio null y explícalo en "notas".
4. Si falta información clave que cambie la estructura o los rendimientos (diámetros, profundidades,
   distancias de transporte, condiciones del terreno, etc.), hazlo en "preguntas" (máximo 3, concretas).
5. Ajusta la propuesta según la CONVERSACIÓN PREVIA si existe.

Responde SOLO con JSON válido:
{{"item_descripcion": "...", "unidad": "...",
  "insumos": [{{"tipo_insumo": "Materiales", "descripcion": "...", "unidad": "m³",
                "rendimiento": 1.02, "precio": 850000.0, "fuente": "Banco: ..."}}],
  "preguntas": ["..."],
  "notas": "..."}}
Sin texto adicional."""
    respuesta = ai_provider.generate_text(prompt, system=_PROMPT_SISTEMA, timeout=120)
    data = _extraer_json_ia(respuesta)
    return data


def _validar_solicitud_borrador(solicitud_id: int) -> dict:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError(f"Solicitud {solicitud_id} no encontrada")
    if solicitud.get("origen") != "constructor":
        raise ValueError("Esta solicitud no proviene del Constructor de APU")
    return solicitud


# ──────────────────────────────────────────────────────────────────
# Pasos del flujo
# ──────────────────────────────────────────────────────────────────

def crear_borrador(descripcion_actividad: str, unidad_actividad: Optional[str] = None,
                   codigo_item: Optional[str] = None, ciudad: Optional[str] = None,
                   proyecto_id: Optional[int] = None, usuario_rol: str = "",
                   usuario_nombre: str = "") -> dict:
    descripcion_actividad = (descripcion_actividad or "").strip()
    if len(descripcion_actividad) < 5:
        raise ValueError("Describe la actividad/ítem con al menos 5 caracteres")

    # Auto-detectar ciudad si no se proporciona explícitamente
    ciudad_detectada = None
    if not ciudad:
        ciudad_detectada = extraer_ciudad_texto(descripcion_actividad)
        if ciudad_detectada:
            ciudad = ciudad_detectada
            log.info(f"Ciudad auto-detectada: {ciudad}")

    solicitud_id = analisis_repo.crear_borrador(
        descripcion_actividad,
        (unidad_actividad or "").strip() or None,
        (codigo_item or "").strip() or None,
        (ciudad or "").strip() or None,
        proyecto_id,
    )
    analisis_repo.insertar_historial(
        solicitud_id, "borrador_creado", usuario_rol or "residente", usuario_nombre or "Residente",
        f"Actividad: {descripcion_actividad[:200]}" + (f" | Ciudad: {ciudad}" if ciudad else ""),
    )
    return {"success": True, "solicitud_id": solicitud_id,
            "mensaje": "Borrador creado. Genera la estructura sugerida con IA."}


def sugerir_estructura(solicitud_id: int) -> dict:
    solicitud = _validar_solicitud_borrador(solicitud_id)
    if solicitud.get("estado") != "borrador":
        raise ValueError(f"Solo se puede sugerir estructura en estado 'borrador' (actual: {solicitud.get('estado')})")

    descripcion = solicitud.get("descripcion_actividad") or ""
    refs = analisis_repo.buscar_apus_similares(descripcion)
    # Consultar referencias SECOP II externas para enriquecer la propuesta con precios de mercado
    secop_refs = consultar_referencias(descripcion, limite=5)
    # Mergear: dar prioridad a las del banco, pero incluir SECOP II al final
    todos_refs = refs + secop_refs
    refs_ranked = _rankear_referencias(todos_refs, ciudad=solicitud.get("ciudad"))
    propuesta = _construir_propuesta(solicitud, refs_ranked)
    # Rellenar insumos sin precio mediante scraping en tiempo real (CYPE Colombia / Mercado)
    propuesta = _rellenar_precios_reales(propuesta, ciudad=solicitud.get("ciudad"))
    return {
        "solicitud_id": solicitud_id,
        "propuesta": propuesta,
        "referencias_usadas": [
            {"item": r.get("item"), "descripcion": r.get("items_descripcion"), "ciudad": r.get("ciudad"),
             "fecha": str(r.get("fecha")) if r.get("fecha") else None, "recencia": r.get("recencia"),
             "precio_unitario": float(r["precio_unitario"]) if r.get("precio_unitario") else None}
            for r in refs_ranked[:4]
        ],
    }


def refinar_propuesta(solicitud_id: int, conversacion: list[dict], propuesta_actual: Optional[dict] = None) -> dict:
    """Itera sobre la propuesta respondiendo preguntas del residente. La conversación
    completa la mantiene el cliente (rol: 'ia' | 'usuario')."""
    solicitud = _validar_solicitud_borrador(solicitud_id)
    if solicitud.get("estado") != "borrador":
        raise ValueError(f"Solo se puede refinar en estado 'borrador' (actual: {solicitud.get('estado')})")
    if not conversacion:
        raise ValueError("La conversación no puede estar vacía")

    descripcion = solicitud.get("descripcion_actividad") or ""
    refs = analisis_repo.buscar_apus_similares(descripcion)
    refs_ranked = _rankear_referencias(refs, ciudad=solicitud.get("ciudad"))

    mensajes = list(conversacion)
    if propuesta_actual:
        mensajes.insert(0, {"rol": "ia", "texto": json.dumps(propuesta_actual, ensure_ascii=False)})
    propuesta = _construir_propuesta(solicitud, refs_ranked, conversacion=mensajes)
    # Rellenar insumos sin precio mediante scraping en tiempo real
    propuesta = _rellenar_precios_reales(propuesta, ciudad=solicitud.get("ciudad"))
    return {"solicitud_id": solicitud_id, "propuesta": propuesta}


def _fila_desde_propuesta(ins: dict, item: str, items_descripcion: str, item_unidad: str) -> dict:
    tipo = (ins.get("tipo_insumo") or "").strip()
    if tipo not in TIPOS_INSUMO_VALIDOS:
        tipo = next((t for t in TIPOS_INSUMO_VALIDOS if t.lower() == tipo.lower()), "Otro")
    descripcion = (ins.get("descripcion") or "").strip()
    if not descripcion:
        raise ValueError("Hay insumos sin descripción en la propuesta")
    rendimiento = ins.get("rendimiento")
    try:
        rendimiento = float(rendimiento) if rendimiento is not None else None
    except (TypeError, ValueError):
        rendimiento = None
    precio = ins.get("precio")
    try:
        precio = float(precio) if precio is not None else None
    except (TypeError, ValueError):
        precio = None
    return {
        "item": item,
        "items_descripcion": items_descripcion,
        "item_unidad": item_unidad,
        "codigo_insumo": (str(ins.get("codigo_insumo")).strip() if ins.get("codigo_insumo") else None),
        "insumo_descripcion": descripcion,
        "insumo_unidad": (ins.get("unidad") or "").strip() or None,
        "rendimiento_insumo": rendimiento,
        "tipo_insumo": tipo,
        "precio_banco": precio,
        "rendimiento_banco": rendimiento,
        "fuente_precio": (ins.get("fuente") or "").strip() or None,
    }


def aplicar_estructura(solicitud_id: int, propuesta: dict, usuario_rol: str = "",
                       usuario_nombre: str = "") -> dict:
    """Persiste la estructura aceptada por el residente como insumos del borrador.
    Los precios quedan pendientes (los aporta el contratista en el paso siguiente);
    el precio del banco se conserva en `precio_banco` para comparar después."""
    solicitud = _validar_solicitud_borrador(solicitud_id)
    if solicitud.get("estado") != "borrador":
        raise ValueError(f"Solo se puede aplicar estructura en estado 'borrador' (actual: {solicitud.get('estado')})")

    insumos = propuesta.get("insumos") or []
    if not insumos:
        raise ValueError("La propuesta no tiene insumos")

    codigo_item = (solicitud.get("codigo_item") or f"NPC-{solicitud_id}").strip()
    items_descripcion = (propuesta.get("item_descripcion") or solicitud.get("descripcion_actividad") or "").strip()
    item_unidad = (propuesta.get("unidad") or solicitud.get("unidad_actividad") or "").strip()

    filas = [_fila_desde_propuesta(i, codigo_item, items_descripcion, item_unidad) for i in insumos]
    analisis_repo.reemplazar_insumos_estructura(solicitud_id, filas)
    analisis_repo.actualizar_tipo_comparacion(solicitud_id, "apu")
    analisis_repo.insertar_historial(
        solicitud_id, "estructura_definida", usuario_rol or "residente", usuario_nombre or "Residente",
        f"Estructura aplicada con {len(filas)} insumo(s).",
    )
    return {"success": True, "insumos": len(filas),
            "mensaje": "Estructura guardada. Registra los precios del contratista."}


def agregar_insumo(solicitud_id: int, insumo: dict) -> dict:
    solicitud = _validar_solicitud_borrador(solicitud_id)
    if solicitud.get("estado") != "borrador":
        raise ValueError("Solo se puede editar la estructura en estado 'borrador'")
    codigo_item = (solicitud.get("codigo_item") or f"NPC-{solicitud_id}").strip()
    items_descripcion = solicitud.get("descripcion_actividad") or ""
    item_unidad = solicitud.get("unidad_actividad") or ""
    fila = _fila_desde_propuesta(insumo, codigo_item, items_descripcion, item_unidad)
    insumo_id = analisis_repo.insertar_insumo_estructura(solicitud_id, fila)
    return {"success": True, "insumo_id": insumo_id}


def eliminar_insumo(solicitud_id: int, insumo_id: int) -> dict:
    solicitud = _validar_solicitud_borrador(solicitud_id)
    if solicitud.get("estado") != "borrador":
        raise ValueError("Solo se puede editar la estructura en estado 'borrador'")
    if not analisis_repo.eliminar_insumo_estructura(solicitud_id, insumo_id):
        raise ValueError(f"Insumo {insumo_id} no encontrado en la solicitud {solicitud_id}")
    return {"success": True}


def registrar_precios(solicitud_id: int, precios: list[dict], usuario_rol: str = "",
                      usuario_nombre: str = "") -> dict:
    """Registra los precios del CONTRATISTA (precio_unitario_apu) por insumo.
    `precios`: [{"insumo_id": int, "precio": float}]."""
    _validar_solicitud_borrador(solicitud_id)
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if solicitud.get("estado") != "borrador":
        raise ValueError("Solo se pueden registrar precios en estado 'borrador'")

    actuales = {i["id"]: i for i in solicitud.get("insumos", [])}
    actualizados, errores = 0, []
    for p in precios or []:
        insumo_id = p.get("insumo_id")
        try:
            precio = float(p.get("precio"))
        except (TypeError, ValueError):
            errores.append(f"Insumo {insumo_id}: precio inválido")
            continue
        if precio < 0:
            errores.append(f"Insumo {insumo_id}: el precio no puede ser negativo")
            continue
        if insumo_id not in actuales:
            errores.append(f"Insumo {insumo_id}: no pertenece a la solicitud")
            continue
        rendimiento = actuales[insumo_id].get("rendimiento_insumo")
        try:
            parcial = round(float(rendimiento) * precio, 6) if rendimiento is not None else None
        except (TypeError, ValueError):
            parcial = None
        analisis_repo.actualizar_precio_insumo(solicitud_id, insumo_id, precio, parcial)
        actualizados += 1

    if actualizados:
        analisis_repo.insertar_historial(
            solicitud_id, "precios_contratista", usuario_rol or "contraparte", usuario_nombre or "Contratista",
            f"Precios registrados para {actualizados} insumo(s).",
        )
        crear_notificacion(
            "analista",
            f"Borrador #{solicitud_id} con precios del contratista",
            f"Se registraron {actualizados} precio(s) del contratista en el borrador #{solicitud_id}. "
            "Pendiente de revisión y envío a análisis.",
            tipo="flujo", solicitud_id=solicitud_id,
            clave_unica=f"precios:{solicitud_id}:{date.today().isoformat()}",
        )
    return {"success": True, "actualizados": actualizados, "errores": errores}


def cargar_precios_archivo(solicitud_id: int, filas_cotizacion: list[dict]) -> dict:
    """Cruza las filas extraídas de la cotización (PDF/Excel) del contratista contra
    los insumos del borrador y aplica los precios emparejados."""
    solicitud = _validar_solicitud_borrador(solicitud_id)
    if solicitud.get("estado") != "borrador":
        raise ValueError("Solo se pueden cargar precios en estado 'borrador'")
    insumos = solicitud.get("insumos", [])
    if not insumos:
        raise ValueError("El borrador no tiene estructura de insumos aún")

    asignadas, sin_coincidencia = _emparejar_filas_cotizacion(filas_cotizacion, insumos)
    for a in asignadas:
        rendimiento = next((i.get("rendimiento_insumo") for i in insumos if i["id"] == a["insumo_id"]), None)
        parcial = round(a["precio"] * float(rendimiento), 6) if rendimiento is not None else None
        analisis_repo.actualizar_precio_insumo(solicitud_id, a["insumo_id"], a["precio"], parcial)

    if asignadas:
        analisis_repo.insertar_historial(
            solicitud_id, "precios_contratista", "contraparte", "Cotización cargada",
            f"Cotización cargada: {len(asignadas)} precio(s) emparejado(s) automáticamente.",
        )
    return {
        "success": True,
        "total_filas": len(filas_cotizacion),
        "asignadas": asignadas,
        "sin_coincidencia": sin_coincidencia,
        "mensaje": f"{len(asignadas)} de {len(filas_cotizacion)} fila(s) emparejada(s).",
    }


def enviar_a_analisis(solicitud_id: int, omitir_sin_precio: bool = False,
                      usuario_rol: str = "", usuario_nombre: str = "") -> dict:
    """Valida el borrador completo (todos los insumos con precio del contratista,
    excluyendo ceros) y lo pasa al análisis comparativo contra el banco."""
    _validar_solicitud_borrador(solicitud_id)
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if solicitud.get("estado") != "borrador":
        raise ValueError(f"El borrador ya fue enviado (estado: {solicitud.get('estado')})")

    insumos = solicitud.get("insumos", [])
    if not insumos:
        raise ValueError("El borrador no tiene estructura de insumos")

    def _precio(ins: dict) -> float:
        try:
            return float(ins.get("precio_unitario_apu") or 0)
        except (TypeError, ValueError):
            return 0.0

    sin_precio = [i for i in insumos if _precio(i) <= 0]
    if sin_precio:
        if not omitir_sin_precio:
            detalle = ", ".join(str(i.get("insumo_descripcion"))[:40] for i in sin_precio[:5])
            raise ValueError(
                f"{len(sin_precio)} insumo(s) sin precio del contratista (se excluyen los ceros): {detalle}. "
                "Completa los precios o repite el envío con omitir_sin_precio=true."
            )
        for i in sin_precio:
            analisis_repo.eliminar_insumo_estructura(solicitud_id, i["id"])
        insumos = [i for i in insumos if _precio(i) > 0]

    if not insumos:
        raise ValueError("No queda ningún insumo con precio válido")

    codigo_item = (solicitud.get("codigo_item") or f"NPC-{solicitud_id}").strip()
    descripcion = (insumos[0].get("items_descripcion") or solicitud.get("descripcion_actividad") or "").strip()
    unidad = (solicitud.get("unidad_actividad") or insumos[0].get("item_unidad") or "").strip()
    analisis_repo.rellenar_datos_item(solicitud_id, codigo_item, descripcion, unidad)

    analisis_repo.insertar_historial(
        solicitud_id, "enviado_a_analisis", usuario_rol or "residente", usuario_nombre or "Residente",
        f"Estructura final: {len(insumos)} insumo(s) con precios del contratista.",
    )

    resultado = realizar_analisis(solicitud_id)
    resultado["insumos_enviados"] = len(insumos)
    return resultado
