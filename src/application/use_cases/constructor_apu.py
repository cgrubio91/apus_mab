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

Orquestador + fachada: la propuesta IA vive en `constructor_propuesta`, los
costos en `constructor_costos`; aquí queda el flujo de borrador/insumos y se
reexporta todo para compatibilidad (`constructor_apu.<nombre>`).
"""

import logging
from datetime import date
from typing import Optional

from src.application.use_cases.constructor_costos import (
    _cargar_serie_indice,
    _mediana,
    _respuesta_propuesta,
    calcular_costo_directo,
    calcular_desglose_aiu,
)
from src.application.use_cases.constructor_propuesta import (
    _PROMPT_SISTEMA,
    RECENCIA_ACEPTABLE_DIAS,
    RECENCIA_BUENA_DIAS,
    RECENCIA_EXCELENTE_DIAS,
    TIPOS_INSUMO_VALIDOS,
    _aplicar_jerarquia_precios,
    _compactar_referencias_para_ia,
    _construir_propuesta,
    _es_indirecto_o_aiu,
    _extraer_json_ia,
    _float_no_negativo,
    _normalizar_propuesta,
    _parse_fecha,
    _precios_por_insumo,
    _puntaje_recencia,
    _rankear_referencias,
    _referencias_para_propuesta,
    _rellenar_precios_reales,
    _rendimientos_por_insumo,
    _validar_solicitud_borrador,
    _validar_solicitud_constructor,
    refinar_propuesta,
    sugerir_estructura,
)
from src.application.use_cases.extract_city import extraer_ciudad_texto
from src.application.use_cases.manage_analisis import realizar_analisis
from src.application.use_cases.notificaciones import crear_notificacion
from src.infrastructure.database.repositories.analisis_repository import (
    _similitud_tokens,
    _tokenizar,
    analisis_repo,
)

log = logging.getLogger("mapus.application.constructor")

__all__ = [
    "RECENCIA_ACEPTABLE_DIAS",
    "RECENCIA_BUENA_DIAS",
    "RECENCIA_EXCELENTE_DIAS",
    "TIPOS_INSUMO_VALIDOS",
    "_PROMPT_SISTEMA",
    "_aplicar_jerarquia_precios",
    "_cargar_serie_indice",
    "_compactar_referencias_para_ia",
    "_construir_propuesta",
    "_emparejar_filas_cotizacion",
    "_es_indirecto_o_aiu",
    "_extraer_json_ia",
    "_fila_desde_propuesta",
    "_float_no_negativo",
    "_mediana",
    "_normalizar_propuesta",
    "_parse_fecha",
    "_precios_por_insumo",
    "_puntaje_recencia",
    "_rankear_referencias",
    "_referencias_para_propuesta",
    "_rellenar_precios_reales",
    "_rendimientos_por_insumo",
    "_respuesta_propuesta",
    "_validar_solicitud_borrador",
    "_validar_solicitud_constructor",
    "actualizar_justificacion",
    "agregar_insumo",
    "aplicar_estructura",
    "calcular_costo_directo",
    "calcular_desglose_aiu",
    "cargar_precios_archivo",
    "crear_borrador",
    "eliminar_insumo",
    "enviar_a_analisis",
    "incorporar_a_proyecto_y_banco",
    "listar_borradores",
    "refinar_propuesta",
    "registrar_precios",
    "sugerir_estructura",
]


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


def listar_borradores(limite: int = 20) -> dict:
    """Borradores del Constructor de APU (más recientes primero)."""
    limite = max(1, min(int(limite or 20), 50))
    rows = analisis_repo.get_solicitudes(estado="borrador", origen="constructor")[:limite]
    return {
        "success": True,
        "borradores": [
            {
                "id": r.get("id"),
                "descripcion_actividad": r.get("descripcion_actividad") or r.get("primer_item"),
                "ciudad": r.get("ciudad"),
                "codigo_item": r.get("codigo_item"),
                "unidad_actividad": r.get("unidad_actividad"),
                "proyecto_id": r.get("proyecto_id"),
                "total_insumos": r.get("total_items") or 0,
                "created_at": r.get("created_at").isoformat() if hasattr(r.get("created_at"), "isoformat") else r.get("created_at"),
            }
            for r in rows
        ],
    }


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
    codigo_item = (solicitud.get("codigo_item") or f"NPC-{solicitud_id}").strip()
    items_descripcion = solicitud.get("descripcion_actividad") or ""
    item_unidad = solicitud.get("unidad_actividad") or ""
    fila = _fila_desde_propuesta(insumo, codigo_item, items_descripcion, item_unidad)
    insumo_id = analisis_repo.insertar_insumo_estructura(solicitud_id, fila)
    return {"success": True, "insumo_id": insumo_id}


def eliminar_insumo(solicitud_id: int, insumo_id: int) -> dict:
    _validar_solicitud_borrador(solicitud_id)
    if not analisis_repo.eliminar_insumo_estructura(solicitud_id, insumo_id):
        raise ValueError(f"Insumo {insumo_id} no encontrado en la solicitud {solicitud_id}")
    return {"success": True}


def registrar_precios(solicitud_id: int, precios: list[dict], usuario_rol: str = "",
                      usuario_nombre: str = "") -> dict:
    """Registra los precios del CONTRATISTA (precio_unitario_apu) por insumo.
    `precios`: [{"insumo_id": int, "precio": float}]."""
    solicitud = _validar_solicitud_borrador(solicitud_id)

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
    solicitud = _validar_solicitud_borrador(solicitud_id)

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


def actualizar_justificacion(solicitud_id: int, justificacion_tecnica: Optional[str] = None,
                            localizacion_obra: Optional[str] = None,
                            numero_acta_aprobacion: Optional[str] = None,
                            fecha_aprobacion_entidad: Optional[str] = None) -> dict:
    _validar_solicitud_constructor(solicitud_id)
    from src.infrastructure.database.connection import execute_query
    updates = []
    params = []
    if justificacion_tecnica is not None:
        updates.append("justificacion_tecnica = %s")
        params.append(justificacion_tecnica)
    if localizacion_obra is not None:
        updates.append("localizacion_obra = %s")
        params.append(localizacion_obra)
    if numero_acta_aprobacion is not None:
        updates.append("numero_acta_aprobacion = %s")
        params.append(numero_acta_aprobacion)
    if fecha_aprobacion_entidad is not None:
        updates.append("fecha_aprobacion_entidad = %s")
        params.append(fecha_aprobacion_entidad or None)

    if updates:
        params.append(solicitud_id)
        execute_query(
            f"UPDATE solicitudes_apu SET {', '.join(updates)} WHERE id = %s",
            tuple(params),
            fetch=False,
        )
    return {"success": True, "solicitud_id": solicitud_id}


def incorporar_a_proyecto_y_banco(solicitud_id: int, proyecto_id: Optional[int] = None,
                                  numero_acta: Optional[str] = None,
                                  fecha_aprobacion: Optional[str] = None,
                                  justificacion: Optional[str] = None,
                                  usuario_rol: str = "residente",
                                  usuario_nombre: str = "Residente Técnico") -> dict:
    """Incorporación formal del APU ya aprobado por la Entidad al proyecto y al banco histórico."""
    from src.infrastructure.database.connection import execute_query
    solicitud = _validar_solicitud_constructor(solicitud_id)
    estado = solicitud.get("estado")
    if solicitud.get("estado_incorporacion") == "incorporado":
        raise ValueError(f"El APU #{solicitud_id} ya fue incorporado al proyecto y al banco")
    if estado not in ("aprobado_legal", "firmado_legal"):
        raise ValueError(
            f"Solo se puede incorporar un APU con firma legal (estado actual: {estado}). "
            "Envíalo primero al flujo de análisis y aprobación."
        )

    insumos = solicitud.get("insumos") or []
    if not insumos:
        raise ValueError("La solicitud no contiene insumos estructurados")

    # Actualizar datos de aprobación si vienen en la llamada
    if justificacion or numero_acta or fecha_aprobacion:
        actualizar_justificacion(
            solicitud_id,
            justificacion_tecnica=justificacion,
            numero_acta_aprobacion=numero_acta,
            fecha_aprobacion_entidad=fecha_aprobacion,
        )

    pid = proyecto_id or solicitud.get("proyecto_id")
    codigo_item = (solicitud.get("codigo_item") or f"NPC-{solicitud_id}").strip()
    nombre_item = (insumos[0].get("items_descripcion") or solicitud.get("descripcion_actividad") or "Ítem No Previsto").strip()
    unidad_item = (solicitud.get("unidad_actividad") or insumos[0].get("item_unidad") or "und").strip()

    # Calcular Costo Directo y AIU
    costo_directo = calcular_costo_directo(insumos)
    desglose = calcular_desglose_aiu(costo_directo, proyecto_id=pid)
    costo_total_item = desglose["valores"]["costo_total"]

    # 1. Incorporar a item_proyecto si hay proyecto asociado
    item_proyecto_id = None
    nombre_proyecto_final = "PROYECTO LOCAL"
    if pid:
        proy_rows = execute_query("SELECT descripcion FROM proyectos WHERE id = %s", (pid,))
        if proy_rows and proy_rows[0].get("descripcion"):
            nombre_proyecto_final = proy_rows[0]["descripcion"]

        # Verificar si ya existe el ítem en el proyecto
        existente = execute_query(
            "SELECT id FROM item_proyecto WHERE proyecto = %s AND apu_solicitud_id = %s",
            (pid, solicitud_id),
        )
        if existente:
            item_proyecto_id = existente[0]["id"]
            execute_query(
                """UPDATE item_proyecto SET valor_unitario = %s, valor_presupuestado = %s,
                          aprobado_interventoria = 1, aprobado_costos = 1
                   WHERE id = %s""",
                (costo_total_item, costo_total_item, item_proyecto_id),
                fetch=False,
            )
        else:
            item_proyecto_id = execute_query(
                """INSERT INTO item_proyecto (proyecto, codigo, nombre, unidad_medida, cantidad_presupuestada,
                                              valor_unitario, valor_presupuestado, apu_solicitud_id,
                                              aprobado_interventoria, aprobado_costos, tipo_item)
                   VALUES (%s, %s, %s, %s, 1.0, %s, %s, %s, 1, 1, 'NP')""",
                (pid, codigo_item, nombre_item, unidad_item, costo_total_item, costo_total_item, solicitud_id),
                fetch=False,
                return_lastrowid=True,
            )

    # 2. Replicar insumos en la tabla `apus` (Banco central de APUs)
    filas_apus = 0
    ciudad = solicitud.get("ciudad") or "Bogotá"
    hoy_str = date.today().isoformat()
    for ins in insumos:
        p_insumo = float(ins.get("precio_unitario_apu") or ins.get("precio_banco") or 0)
        rend = float(ins.get("rendimiento_insumo") or 1)
        parcial = round(p_insumo * rend, 2)
        desc_ins = ins.get("insumo_descripcion") or "Insumo"
        cod_ins = ins.get("codigo_insumo") or ""
        tipo_ins = ins.get("tipo_insumo") or "Materiales"
        und_ins = ins.get("insumo_unidad") or "und"
        obs = f"Aprobado por Entidad (Acta {numero_acta or 'S/N'}) vía Solicitud #{solicitud_id}"

        execute_query(
            """INSERT INTO apus (
                   nombre_proyecto, proyecto_id, ciudad, pais, entidad, contratista,
                   item, items_descripcion, item_unidad, precio_unitario, precio_unitario_sin_aiu,
                   codigo_insumo, tipo_insumo, insumo_descripcion, insumo_unidad,
                   rendimiento_insumo, precio_unitario_apu, precio_parcial_apu,
                   fecha_aprobacion_apu, observacion
               ) VALUES (%s, %s, %s, 'Colombia', 'Entidad Contratante', %s,
                         %s, %s, %s, %s, %s,
                         %s, %s, %s, %s,
                         %s, %s, %s,
                         %s, %s)""",
            (nombre_proyecto_final, pid, ciudad, solicitud.get("contratista") or "Contratista de Obra",
             codigo_item, nombre_item, unidad_item, costo_total_item, costo_directo,
             cod_ins, tipo_ins, desc_ins, und_ins,
             rend, p_insumo, parcial,
             hoy_str, obs),
            fetch=False,
        )
        filas_apus += 1

    # 3. Actualizar estado en solicitudes_apu
    execute_query(
        """UPDATE solicitudes_apu SET
               estado = 'firmado_legal',
               estado_incorporacion = 'incorporado',
               proyecto_id = COALESCE(%s, proyecto_id)
           WHERE id = %s""",
        (pid, solicitud_id),
        fetch=False,
    )

    # 4. Registrar en historial
    analisis_repo.insertar_historial(
        solicitud_id, "incorporado_proyecto", usuario_rol, usuario_nombre,
        f"APU incorporado exitosamente al proyecto '{nombre_proyecto_final}' y al banco de APUs ({filas_apus} filas creadas). Valor unitario total con AIU: ${costo_total_item:,.2f}."
    )

    crear_notificacion(
        "subgerente",
        f"APU #{solicitud_id} incorporado al proyecto",
        f"El APU '{nombre_item}' fue incorporado al proyecto y al banco con valor unitario ${costo_total_item:,.2f}.",
        tipo="flujo", solicitud_id=solicitud_id,
    )

    return {
        "success": True,
        "solicitud_id": solicitud_id,
        "proyecto_id": pid,
        "item_proyecto_id": item_proyecto_id,
        "filas_banco_creadas": filas_apus,
        "costo_directo": costo_directo,
        "costo_total_unitario": costo_total_item,
        "desglose_aiu": desglose,
        "mensaje": f"APU #{solicitud_id} incorporado formalmente al proyecto y al banco de APUs.",
    }
