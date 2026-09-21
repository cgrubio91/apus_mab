"""Application: Constructor de APU — propuesta IA y ranking de referencias.

Submódulo de `constructor_apu`: propuesta de estructura con IA, jerarquía de
precios y agregados del banco (medianas de rendimientos/precios).
Reexportado desde `constructor_apu` para compatibilidad.
"""

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Optional

from src.application.use_cases.constructor_costos import (
    _cargar_serie_indice,
    _mediana,
    _respuesta_propuesta,
)
from src.application.use_cases.ingesta_referencias import consultar_referencias
from src.infrastructure.ai.provider import ai_provider
from src.infrastructure.database.repositories.analisis_repository import _tokenizar, analisis_repo
from src.infrastructure.pricing.indexacion import indexar_observaciones
from src.infrastructure.scraping.catalogo_materiales import FUENTE as FUENTE_HOMECENTER

log = logging.getLogger("mapus.application.constructor_propuesta")

TIPOS_INSUMO_VALIDOS = ["Materiales", "Equipos", "Mano de obra", "Transporte", "Herramienta", "Otro"]

# Enlace de respaldo cuando la referencia CYPE no trae la página de la que salió el precio.
CYPE_BASE_WEB = "https://colombia.generadordeprecios.info/"


def _es_indirecto_o_aiu(desc: Optional[str] = None, tipo: Optional[str] = None) -> bool:
    """Detecta si un insumo corresponde a costos indirectos o A.I.U.
    (Administración, Imprevistos, Utilidad), los cuales NO deben ir en la tabla
    de costos directos del APU sino en la cascada contractual de A.I.U."""
    t = (tipo or "").strip().lower()
    if t in ("indirectos", "indirecto"):
        return True
    d = (desc or "").strip().lower()
    terminos_aiu = [
        "administracion", "administración", "imprevisto", "imprevistos",
        "utilidad", "utilidades", "a.i.u", "aiu", "a.i.u.",
    ]
    for term in terminos_aiu:
        if term in ("aiu", "a.i.u"):
            if re.search(r"\b(a\.?i\.?u\.?)\b", d):
                return True
        elif term in d:
            return True
    return False

# Ventanas de vigencia para preferir referencias del banco (días).
RECENCIA_EXCELENTE_DIAS = 180      # ≤ 6 meses
RECENCIA_BUENA_DIAS = 365          # ≤ 12 meses
RECENCIA_ACEPTABLE_DIAS = 730      # ≤ 24 meses


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


def _float_no_negativo(valor) -> Optional[float]:
    try:
        if valor is None or valor == "":
            return None
        n = float(valor)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _normalizar_propuesta(propuesta: dict) -> dict:
    """Sanea el JSON de la IA: tipos de insumo válidos, números y preguntas ≤ 3."""
    if not isinstance(propuesta, dict):
        raise ValueError("La propuesta de IA no es un objeto válido")
    insumos = []
    for ins in propuesta.get("insumos") or []:
        if not isinstance(ins, dict):
            continue
        descripcion = (ins.get("descripcion") or "").strip()
        if not descripcion:
            continue
        tipo = (ins.get("tipo_insumo") or "").strip()
        if _es_indirecto_o_aiu(descripcion, tipo):
            continue
        if tipo not in TIPOS_INSUMO_VALIDOS:
            tipo = next((t for t in TIPOS_INSUMO_VALIDOS if t.lower() == tipo.lower()), "Otro")
        insumos.append({
            "tipo_insumo": tipo,
            "descripcion": descripcion,
            "unidad": (ins.get("unidad") or "").strip() or None,
            "rendimiento": _float_no_negativo(ins.get("rendimiento")),
            "precio": _float_no_negativo(ins.get("precio")),
            "fuente": (ins.get("fuente") or "").strip() or None,
            "codigo_insumo": (str(ins.get("codigo_insumo")).strip() if ins.get("codigo_insumo") else None),
        })
    preguntas = propuesta.get("preguntas") or []
    if not isinstance(preguntas, list):
        preguntas = []
    preguntas = [str(p).strip() for p in preguntas if str(p).strip()][:3]
    return {
        "item_descripcion": (propuesta.get("item_descripcion") or "").strip(),
        "unidad": (propuesta.get("unidad") or "").strip() or None,
        "insumos": insumos,
        "preguntas": preguntas,
        "notas": (propuesta.get("notas") or "").strip() or None,
    }


# ──────────────────────────────────────────────────────────────────
# Propuesta IA
# ──────────────────────────────────────────────────────────────────

def _compactar_referencias_para_ia(refs_ranked: list[dict], max_refs: int = 4,
                                   max_insumos_por_ref: int = 20) -> list[dict]:
    salida = []
    for r in refs_ranked[:max_refs]:
        insumos = []
        for ins in (r.get("insumos") or [])[:max_insumos_por_ref]:
            desc = ins.get("insumo_descripcion")
            tipo = ins.get("tipo_insumo")
            if _es_indirecto_o_aiu(desc, tipo):
                continue
            precio = ins.get("precio_unitario_apu")
            insumos.append({
                "tipo": tipo,
                "desc": desc,
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


def _rendimientos_por_insumo(refs_ranked: list[dict], max_refs: int = 6,
                             min_muestras: int = 2) -> list[dict]:
    """Agrega los rendimientos del banco por insumo para que la propuesta use la
    MEDIANA (robusta a outliers) y no el rendimiento de un único APU.

    Agrupa por el token más distintivo (más largo) de la descripción del insumo
    —siguiendo la misma heurística de emparejamiento del resto del módulo— y
    devuelve, por grupo con al menos `min_muestras` datos: mediana, n, min y max.
    """
    grupos: dict = {}
    for r in refs_ranked[:max_refs]:
        for ins in (r.get("insumos") or []):
            desc = (ins.get("insumo_descripcion") or "").strip()
            tipo = ins.get("tipo_insumo")
            if _es_indirecto_o_aiu(desc, tipo):
                continue
            rend = ins.get("rendimiento_insumo")
            try:
                rend = float(rend)
            except (TypeError, ValueError):
                continue
            if rend <= 0:
                continue
            tokens = _tokenizar(desc)
            if not tokens:
                continue
            clave = max(tokens, key=len)
            g = grupos.setdefault(clave, {"descripcion": desc, "valores": []})
            g["valores"].append(rend)

    salida = []
    for clave, g in grupos.items():
        vals = g["valores"]
        if len(vals) < min_muestras:
            continue
        salida.append({
            "insumo": g["descripcion"],
            "clave": clave,
            "rendimiento_mediana": _mediana(vals),
            "n": len(vals),
            "min": round(min(vals), 6),
            "max": round(max(vals), 6),
        })
    salida.sort(key=lambda d: d["n"], reverse=True)
    return salida


def _precios_por_insumo(refs_ranked: list[dict], serie_indice: Optional[dict] = None,
                        hoy=None, max_refs: int = 6, min_muestras: int = 1) -> list[dict]:
    """Agrega los precios de insumo del banco y los lleva a PESOS DE HOY con la
    serie de índices (DANE ICCP/IPC). Devuelve, por insumo, la MEDIANA indexada
    con nº de muestras y rango. Si no hay serie, deja los precios nominales.

    Agrupa por el token más distintivo, como `_rendimientos_por_insumo`.
    """
    serie_indice = serie_indice or {}
    grupos: dict = {}
    for r in refs_ranked[:max_refs]:
        fecha_ref = r.get("fecha")
        for ins in (r.get("insumos") or []):
            desc = (ins.get("insumo_descripcion") or "").strip()
            tipo = ins.get("tipo_insumo")
            if _es_indirecto_o_aiu(desc, tipo):
                continue
            precio = ins.get("precio_unitario_apu")
            try:
                precio = float(precio)
            except (TypeError, ValueError):
                continue
            if precio <= 0:
                continue
            tokens = _tokenizar(desc)
            if not tokens:
                continue
            clave = max(tokens, key=len)
            g = grupos.setdefault(clave, {"descripcion": desc, "obs": []})
            g["obs"].append({"precio": precio, "fecha": ins.get("fecha") or fecha_ref})

    salida = []
    for clave, g in grupos.items():
        obs = g["obs"]
        if len(obs) < min_muestras:
            continue
        indexadas = indexar_observaciones(obs, serie_indice, hoy) if serie_indice else obs
        precios = [o["precio"] for o in indexadas]
        salida.append({
            "insumo": g["descripcion"],
            "clave": clave,
            "precio_mediana_hoy": _mediana(precios),
            "n": len(precios),
            "min": round(min(precios), 2),
            "max": round(max(precios), 2),
            "indexado": bool(serie_indice),
        })
    salida.sort(key=lambda d: d["n"], reverse=True)
    return salida


_PROMPT_SISTEMA = "Eres un ingeniero civil experto en Análisis de Precios Unitarios (APU) de obra civil en Colombia."


def _construir_propuesta(solicitud: dict, refs_ranked: list[dict],
                         conversacion: Optional[list[dict]] = None,
                         serie_indice: Optional[dict] = None) -> dict:
    """Llama a la IA para proponer la estructura del APU. Devuelve el JSON de la
    propuesta (insumos + preguntas) junto con las referencias usadas."""
    descripcion = solicitud.get("descripcion_actividad") or ""
    ciudad = solicitud.get("ciudad")
    precios_ref = _precios_por_insumo(refs_ranked, serie_indice=serie_indice)
    hay_indexado = any(p.get("indexado") for p in precios_ref)
    etiqueta_precios = ("a PESOS DE HOY (indexada con DANE)" if hay_indexado
                        else "NOMINAL — sin serie de índices cargada")
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

REFERENCIAS DEL BANCO DE APUs (ordenadas por relevancia: similitud, cercanía a la ciudad y recencia;
el campo "recencia" indica qué tan viejo está el dato):
{json.dumps(_compactar_referencias_para_ia(refs_ranked), default=str, ensure_ascii=False, indent=2)}

RENDIMIENTOS DE REFERENCIA (MEDIANA del banco por insumo, con nº de muestras y rango):
{json.dumps(_rendimientos_por_insumo(refs_ranked), default=str, ensure_ascii=False, indent=2)}

PRECIOS DE REFERENCIA POR INSUMO (MEDIANA {etiqueta_precios}, con nº de muestras y rango):
{json.dumps(precios_ref, default=str, ensure_ascii=False, indent=2)}

INSTRUCCIONES:
1. Propón ÚNICAMENTE la ESTRUCTURA DE COSTOS DIRECTOS del APU para esta actividad: lista de insumos por tipo
   ({", ".join(TIPOS_INSUMO_VALIDOS)}), con unidad, RENDIMIENTO (usa 1 cuando el insumo entra por cantidad
   directa, ej. materiales medidos en m³) y PRECIO UNITARIO.
   REGLA OBLIGATORIA: NUNCA incluyas ítems de "Administración", "Imprevistos", "Utilidad", "Indirectos" ni "A.I.U.".
   El A.I.U. se liquida de forma separada y automática en el pie del APU sobre el Costo Directo total según los
   parámetros contractuales del proyecto. Todos los insumos aquí deben ser estrictamente costos directos de ejecución.
2. JERARQUÍA ESTRICTA DE FUENTES PARA PRECIOS:
   - 1ª Prioridad (CYPE Colombia): Aplica para mano de obra (jornales/hora de oficial, obrero, ayudante) y materiales estándar de mercado vigentes. Rotula la fuente como "CYPE Colombia".
   - 3ª Prioridad (Banco de APUs): Si no está en las anteriores, usa la MEDIANA indexada del banco histórico de APUs, rotulando "Banco: <proyecto> · <ciudad>".
   - Si no hay referencia en ninguna fuente, deja el precio en null y fuente "Pendiente cotización contratista".
   Para el RENDIMIENTO, cuando el insumo aparezca en "RENDIMIENTOS DE REFERENCIA" usa la MEDIANA
   (es robusta a datos atípicos), no el valor de un solo APU; ten en cuenta el nº de muestras (n).
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
    return _normalizar_propuesta(_extraer_json_ia(respuesta))


def _aplicar_jerarquia_precios(propuesta: dict, solicitud: dict,
                               refs_ranked: Optional[list[dict]] = None,
                               precios_ref_banco: Optional[Any] = None,
                               cype_source: Optional[Any] = None,
                               referencia_externa_repo: Optional[Any] = None,
                               materiales_source: Optional[Any] = None,
                               proveedor_repo_: Optional[Any] = None) -> dict:
    """Aplica la jerarquía obligatoria de precios por insumo:
       1º CYPE Colombia (tarifas oficiales y de mercado vigentes)
       2º Banco de APUs (mediana histórica indexada a pesos de hoy o referencias del banco)
       3º Catálogo de Materiales Comerciales en Vivo (Homecenter Colombia y marcas de ferretería)
       5º Sin precio (null, pendiente de cotización por contratista)
    """
    ciudad_txt = (solicitud.get("ciudad") or "").strip()
    if isinstance(precios_ref_banco, dict):
        precios_banco_dict = precios_ref_banco
    else:
        precios_banco_dict = {p["clave"]: p for p in (precios_ref_banco or []) if "clave" in p}

    cype_src = cype_source
    if cype_src is None:
        try:
            from src.infrastructure.scraping.cype_source import CypeSource
            cype_src = CypeSource(timeout=3)
        except Exception:
            cype_src = None

    if referencia_externa_repo is None:
        try:
            from src.infrastructure.database.repositories.referencia_externa_repository import (
                referencia_externa_repo as ext_repo,
            )
            referencia_externa_repo = ext_repo
        except Exception:
            referencia_externa_repo = None

    mat_src = materiales_source
    if mat_src is None:
        try:
            from src.infrastructure.scraping.catalogo_materiales import CatalogoMaterialesSource
            mat_src = CatalogoMaterialesSource(timeout=5)
        except Exception:
            mat_src = None

    for ins in propuesta.get("insumos", []):
        desc = (ins.get("descripcion") or "").strip()
        tipo = (ins.get("tipo_insumo") or "").strip()
        if not desc:
            continue

        # A quién pedir la cotización: el directorio IDU se sugiere para todos los
        # insumos (tengan o no precio en el banco), porque el nombre del proveedor
        # nunca va a coincidir literal con la descripción del insumo.
        _sugerir_proveedores(ins, ciudad_txt, proveedor_repo_=proveedor_repo_)

        asignado = False

        # ── 1ª PRIORIDAD: CYPE COLOMBIA ──
        if cype_src:
            try:
                ref_cype = cype_src.buscar_referencia_insumo(desc, tipo)
                if ref_cype and ref_cype.get("precio") is not None and float(ref_cype["precio"]) > 0:
                    ins["precio"] = float(ref_cype["precio"])
                    fuente = ref_cype.get("fuente", "CYPE Colombia")
                    if ciudad_txt and "zona" not in fuente.lower():
                        fuente = f"{fuente} · zona {ciudad_txt}"
                    ins["fuente"] = fuente
                    # Enlace a la página CYPE de la que salió el precio. Los precios de la
                    # tabla de tarifas fijas no tienen página propia y caen a la portada.
                    ins["fuente_link"] = ref_cype.get("url") or CYPE_BASE_WEB
                    if ref_cype.get("unidad") and not ins.get("unidad"):
                        ins["unidad"] = ref_cype["unidad"]
                    asignado = True
            except Exception:
                pass

        if asignado:
            continue

        # ── 2ª PRIORIDAD: BANCO DE PRECIOS DE REFERENCIA DEL IDU ──
        # Precio oficial de la entidad, con período de publicación: mejor soporte
        # ante interventoría que el histórico del banco, que mezcla varios años.
        if _usar_precio_idu(ins, desc, proveedor_repo_=proveedor_repo_):
            continue

        # ── 3ª PRIORIDAD: BANCO DE APUs (Histórico) ──
        tokens = _tokenizar(desc)
        candidatos_clave = list(tokens)
        if desc.lower().strip() not in candidatos_clave:
            candidatos_clave.append(desc.lower().strip())

        for k in candidatos_clave:
            for b_key in precios_banco_dict:
                if k == b_key or k in b_key or b_key in k:
                    b_info = precios_banco_dict[b_key]
                    p_val = b_info.get("precio_mediana_hoy") if isinstance(b_info, dict) else b_info
                    if p_val is not None and float(p_val) > 0:
                        ins["precio"] = float(p_val)
                        n_muestras = b_info.get("n", 1) if isinstance(b_info, dict) else 1
                        ins["fuente"] = f"Banco de APUs: Mediana histórica ({n_muestras} muestra{'s' if n_muestras > 1 else ''})"
                        ins["fuente_link"] = "/banco-apus"
                        asignado = True
                        break
            if asignado:
                break

        if not asignado and ins.get("precio") is not None and float(ins["precio"]) > 0:
            fuente_ia = (ins.get("fuente") or "").strip()
            if not fuente_ia or ("cype" not in fuente_ia.lower() and "homecenter" not in fuente_ia.lower()):
                ins["fuente"] = fuente_ia if fuente_ia.startswith("Banco") else f"Banco de APUs: {fuente_ia or 'Referencia histórica'}"
                ins["fuente_link"] = "/banco-apus"
                asignado = True

        if asignado:
            continue

        # ── 3ª PRIORIDAD: CATÁLOGO EN VIVO HOMECENTER / CONSTRUCTOR (Materiales Comerciales) ──
        if mat_src and (not tipo or tipo.lower() in ("materiales", "material", "herramienta", "herramientas", "otro")):
            try:
                ref_mat = mat_src.buscar_referencia(desc, tipo)
                if ref_mat and ref_mat.get("precio") is not None and float(ref_mat["precio"]) > 0:
                    ins["precio"] = float(ref_mat["precio"])
                    ins["fuente"] = ref_mat.get("fuente", FUENTE_HOMECENTER)
                    ins["fuente_link"] = ref_mat.get("fuente_link") or "https://www.homecenter.com.co"
                    if ref_mat.get("unidad") and not ins.get("unidad"):
                        ins["unidad"] = ref_mat["unidad"]
                    asignado = True
            except Exception:
                pass

        if asignado:
            continue

        # ── SIN PRECIO: queda pendiente de cotización por el contratista ──
        if not asignado:
            ins["precio"] = None
            if not ins.get("fuente"):
                ins["fuente"] = "Pendiente cotización contratista"

    return propuesta


def _repo_proveedores(proveedor_repo_=None):
    """Repo del directorio IDU, importado perezosamente (los tests lo inyectan)."""
    if proveedor_repo_ is not None:
        return proveedor_repo_
    try:
        from src.infrastructure.database.repositories.proveedor_repository import (
            proveedor_repo as repo_por_defecto,
        )
        return repo_por_defecto
    except Exception:
        return None


def _usar_precio_idu(ins: dict, desc: str, proveedor_repo_=None) -> bool:
    """Cotiza el insumo con el Banco de Precios de Referencia del IDU.

    Devuelve True si asignó precio. El BPR no publica una página por insumo, así
    que no se fija `fuente_link`: el soporte es el código del insumo y el período.
    """
    repo = _repo_proveedores(proveedor_repo_)
    if repo is None:
        return False
    try:
        match = repo.buscar_grupo_de_insumo(desc)
    except Exception:
        log.debug("Fallo consultando el BPR para '%s'", desc, exc_info=True)
        return False

    if not match or match.get("precio") is None or float(match["precio"]) <= 0:
        return False

    ins["precio"] = float(match["precio"])
    codigo = match.get("codigo_idu") or "s/código"
    ins["fuente"] = f"Banco de Precios IDU · {codigo}"
    ins["codigo_insumo"] = ins.get("codigo_insumo") or codigo
    if match.get("unidad") and not ins.get("unidad"):
        ins["unidad"] = match["unidad"]
    return True


def _sugerir_proveedores(ins: dict, ciudad: Optional[str], proveedor_repo_=None) -> None:
    """Adjunta al insumo los proveedores del directorio IDU que podrían cotizarlo.

    Se llama para todos los insumos (haya o no precio): sirve de guía para pedir
    la cotización al contratista. No fija precio: el directorio no los tiene. Solo
    cuando el insumo quedó sin precio convierte la fuente en "Pendiente cotización
    · Sugeridos: ..." (con precio, la fuente de la que salió se respeta).
    """
    if ins.get("proveedores_sugeridos"):
        return
    repo = _repo_proveedores(proveedor_repo_)
    if repo is None:
        return
    desc = (ins.get("descripcion") or ins.get("insumo_descripcion") or "").strip()
    if not desc:
        return
    try:
        sugerencia = repo.sugerir_para_insumo(desc, ciudad=ciudad)
    except Exception:
        log.debug("No se pudieron sugerir proveedores para '%s'", desc, exc_info=True)
        return
    if not sugerencia:
        return

    ins["proveedores_sugeridos"] = sugerencia["proveedores"]
    ins["grupo_proveedores"] = sugerencia["grupo"]

    tiene_precio = (float(ins.get("precio") or 0) > 0) or (float(ins.get("precio_banco") or 0) > 0)
    if not tiene_precio:
        nombres = ", ".join(p["nombre"] for p in sugerencia["proveedores"][:2])
        if nombres:
            ins["fuente"] = f"Pendiente cotización · Sugeridos: {nombres}"


def _rellenar_precios_reales(propuesta: dict, ciudad: Optional[str] = None,
                            solicitud: Optional[dict] = None) -> dict:
    """Compatibilidad con tests y llamadas heredadas. Delega a la jerarquía de precios."""
    sol = dict(solicitud or {})
    if ciudad and not sol.get("ciudad"):
        sol["ciudad"] = ciudad
    return _aplicar_jerarquia_precios(propuesta=propuesta, solicitud=sol)


def _validar_solicitud_constructor(solicitud_id: int) -> dict:
    solicitud = analisis_repo.get_solicitud(solicitud_id)
    if not solicitud:
        raise ValueError(f"Solicitud {solicitud_id} no encontrada")
    if solicitud.get("origen") != "constructor":
        raise ValueError("Esta solicitud no proviene del Constructor de APU")
    return solicitud


def _validar_solicitud_borrador(solicitud_id: int) -> dict:
    solicitud = _validar_solicitud_constructor(solicitud_id)
    if solicitud.get("estado") != "borrador":
        raise ValueError(f"La solicitud debe estar en 'borrador' (actual: {solicitud.get('estado')})")
    return solicitud


def _referencias_para_propuesta(solicitud: dict) -> list[dict]:
    descripcion = solicitud.get("descripcion_actividad") or ""
    refs_externas = consultar_referencias(descripcion, limite=5)
    refs_internos = analisis_repo.buscar_apus_similares(descripcion)
    return _rankear_referencias(refs_externas + refs_internos, ciudad=solicitud.get("ciudad"))


def sugerir_estructura(solicitud_id: int, porcentajes_aiu: Optional[dict] = None) -> dict:
    solicitud = _validar_solicitud_borrador(solicitud_id)
    refs_ranked = _referencias_para_propuesta(solicitud)
    serie_indice = _cargar_serie_indice()
    precios_ref = _precios_por_insumo(refs_ranked, serie_indice=serie_indice)
    propuesta = _construir_propuesta(solicitud, refs_ranked, serie_indice=serie_indice)
    propuesta = _aplicar_jerarquia_precios(propuesta, solicitud, refs_ranked=refs_ranked, precios_ref_banco=precios_ref)
    return _respuesta_propuesta(solicitud_id, solicitud, propuesta, refs_ranked, porcentajes_aiu=porcentajes_aiu)


def refinar_propuesta(solicitud_id: int, conversacion: list[dict], propuesta_actual: Optional[dict] = None,
                      porcentajes_aiu: Optional[dict] = None) -> dict:
    """Itera sobre la propuesta respondiendo preguntas del residente. La conversación
    completa la mantiene el cliente (rol: 'ia' | 'usuario')."""
    solicitud = _validar_solicitud_borrador(solicitud_id)
    if not conversacion:
        raise ValueError("La conversación no puede estar vacía")

    refs_ranked = _referencias_para_propuesta(solicitud)
    serie_indice = _cargar_serie_indice()
    precios_ref = _precios_por_insumo(refs_ranked, serie_indice=serie_indice)
    mensajes = list(conversacion)[-12:]
    if propuesta_actual:
        mensajes.insert(0, {"rol": "ia", "texto": json.dumps(propuesta_actual, ensure_ascii=False)[:8000]})
    propuesta = _construir_propuesta(solicitud, refs_ranked, conversacion=mensajes,
                                     serie_indice=serie_indice)
    propuesta = _aplicar_jerarquia_precios(propuesta, solicitud, refs_ranked=refs_ranked, precios_ref_banco=precios_ref)
    return _respuesta_propuesta(solicitud_id, solicitud, propuesta, refs_ranked, porcentajes_aiu=porcentajes_aiu)
