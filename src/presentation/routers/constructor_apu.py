"""
Presentation: Constructor de APU Routes

Flujo liderado por el residente: borrador → estructura sugerida por IA →
precios del contratista → análisis comparativo contra el banco.
"""

import asyncio
import logging
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from src.application.use_cases import constructor_apu
from src.presentation.auth import require_role


class BorradorCreate(BaseModel):
    descripcion_actividad: str = Field(..., min_length=5, max_length=1000)
    unidad_actividad: Optional[str] = Field(None, max_length=20)
    codigo_item: Optional[str] = Field(None, max_length=100)
    ciudad: Optional[str] = Field(None, max_length=100)
    proyecto_id: Optional[int] = None


class RefinarRequest(BaseModel):
    conversacion: List[dict] = Field(..., description="Historial [{rol: 'ia'|'usuario', texto}]")
    propuesta_actual: Optional[dict] = None


class AplicarEstructuraRequest(BaseModel):
    propuesta: dict


class InsumoCreate(BaseModel):
    tipo_insumo: str
    descripcion: str
    unidad: Optional[str] = None
    rendimiento: Optional[float] = None
    precio: Optional[float] = None
    fuente: Optional[str] = None
    codigo_insumo: Optional[str] = None


class PrecioItem(BaseModel):
    insumo_id: int
    precio: float = Field(ge=0)


class RegistrarPreciosRequest(BaseModel):
    precios: List[PrecioItem]


class EnviarAnalisisRequest(BaseModel):
    omitir_sin_precio: bool = False


log = logging.getLogger("mapus.presentation.constructor")
router = APIRouter()

# El residente (nivel analista) lidera la construcción; la contraparte/inspector
# registra los precios del contratista.
_ROL_RESIDENTE = require_role("analista")
_ROL_CONTRAPARTE = require_role("contraparte")


@router.get("/constructor-apu", tags=["Constructor APU"])
async def listar_borradores(user: dict = Depends(_ROL_RESIDENTE)) -> dict:
    try:
        return constructor_apu.listar_borradores()
    except Exception:
        log.exception("Error listando borradores del Constructor de APU")
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


@router.post("/constructor-apu", tags=["Constructor APU"])
async def crear_borrador(payload: BorradorCreate, user: dict = Depends(_ROL_RESIDENTE)) -> dict:
    try:
        return constructor_apu.crear_borrador(
            payload.descripcion_actividad, payload.unidad_actividad, payload.codigo_item,
            payload.ciudad, payload.proyecto_id, user["rol"], user["nombre"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        log.exception("Error creando borrador de APU")
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


def _obtener_status_error(e: Exception) -> int:
    """Extrae el código de estado de cualquier excepción de requests/Http."""
    status = 0
    try:
        if hasattr(e, 'response') and e.response is not None:
            status = e.response.status_code
        elif hasattr(e, 'status'):
            status = e.status
    except Exception:
        pass
    return status


@router.post("/constructor-apu/{solicitud_id}/sugerir", tags=["Constructor APU"])
async def sugerir_estructura(solicitud_id: int, user: dict = Depends(_ROL_RESIDENTE)) -> dict:
    try:
        return await asyncio.to_thread(constructor_apu.sugerir_estructura, solicitud_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.exceptions.HTTPError as e:
        status_code = _obtener_status_error(e)
        if status_code in (429, 500, 503):
            log.warning("Gemini API overloaded for solicitud %d after retries", solicitud_id)
            raise HTTPException(
                status_code=503,
                detail="El servicio de IA está temporalmente saturado. Espera 30 segundos y vuelve a intentarlo.",
            )
        log.exception("HTTP error sugiriendo estructura para solicitud %d", solicitud_id)
        raise HTTPException(status_code=502, detail="Error de comunicación con el servicio de IA. Intenta nuevamente.")
    except Exception as e:
        status_code = _obtener_status_error(e)
        if status_code in (429, 500, 503):
            log.warning("Gemini API overloaded (non-HTTPError) for solicitud %d after retries", solicitud_id)
            raise HTTPException(
                status_code=503,
                detail="El servicio de IA está temporalmente saturado. Espera 30 segundos y vuelve a intentarlo.",
            )
        log.exception("Error sugiriendo estructura para solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="No se pudo generar la propuesta. Intenta nuevamente.")


@router.post("/constructor-apu/{solicitud_id}/refinar", tags=["Constructor APU"])
async def refinar_propuesta(solicitud_id: int, payload: RefinarRequest, user: dict = Depends(_ROL_RESIDENTE)) -> dict:
    try:
        return await asyncio.to_thread(
            constructor_apu.refinar_propuesta, solicitud_id, payload.conversacion, payload.propuesta_actual,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        log.exception("Error refinando propuesta para solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="No se pudo refinar la propuesta. Intenta nuevamente.")


@router.post("/constructor-apu/{solicitud_id}/estructura", tags=["Constructor APU"])
async def aplicar_estructura(solicitud_id: int, payload: AplicarEstructuraRequest,
                             user: dict = Depends(_ROL_RESIDENTE)) -> dict:
    try:
        return constructor_apu.aplicar_estructura(solicitud_id, payload.propuesta, user["rol"], user["nombre"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        log.exception("Error aplicando estructura a solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


@router.post("/constructor-apu/{solicitud_id}/insumos", tags=["Constructor APU"])
async def agregar_insumo(solicitud_id: int, payload: InsumoCreate, user: dict = Depends(_ROL_RESIDENTE)) -> dict:
    try:
        return constructor_apu.agregar_insumo(solicitud_id, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        log.exception("Error agregando insumo a solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


@router.delete("/constructor-apu/{solicitud_id}/insumos/{insumo_id}", tags=["Constructor APU"])
async def eliminar_insumo(solicitud_id: int, insumo_id: int, user: dict = Depends(_ROL_RESIDENTE)) -> dict:
    try:
        return constructor_apu.eliminar_insumo(solicitud_id, insumo_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        log.exception("Error eliminando insumo %d de solicitud %d", insumo_id, solicitud_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


@router.post("/constructor-apu/{solicitud_id}/precios", tags=["Constructor APU"])
async def registrar_precios(solicitud_id: int, payload: RegistrarPreciosRequest,
                            user: dict = Depends(_ROL_CONTRAPARTE)) -> dict:
    try:
        return constructor_apu.registrar_precios(solicitud_id, [p.model_dump() for p in payload.precios],
                                                 user["rol"], user["nombre"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        log.exception("Error registrando precios en solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


@router.post("/constructor-apu/{solicitud_id}/precios-archivo", tags=["Constructor APU"])
async def cargar_precios_archivo(solicitud_id: int, file: UploadFile = File(...),
                                 user: dict = Depends(_ROL_CONTRAPARTE)) -> dict:
    """Extrae las filas de la cotización (PDF/Excel) y las empareja con la estructura
    del borrador para llenar los precios del contratista automáticamente."""
    filename = file.filename or "cotizacion"
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ("pdf", "xlsx", "xls"):
        raise HTTPException(status_code=400, detail="Formato no soportado. Use PDF o Excel.")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máx 50 MB)")

    import os
    import tempfile
    suffix = f".{ext}"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        def _extraer() -> list[dict]:
            from src.infrastructure.ai.gemini_extractor import (
                extract_apus_from_excel,
                extract_apus_from_pdf_batched,
                post_process_extracted_data,
            )
            if ext == "pdf":
                raw = extract_apus_from_pdf_batched(tmp_path, filename)
            else:
                raw = extract_apus_from_excel(tmp_path, filename)
            return post_process_extracted_data(raw, filename)

        filas = await asyncio.to_thread(_extraer)
    except HTTPException:
        raise
    except Exception:
        log.exception("Error extrayendo cotización %s para solicitud %d", filename, solicitud_id)
        raise HTTPException(status_code=500, detail="No se pudo leer la cotización. Verifica la tabla de insumos.")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except PermissionError:
                pass

    if not filas:
        raise HTTPException(status_code=400, detail="La cotización no contiene filas de insumos reconocibles.")

    try:
        return await asyncio.to_thread(constructor_apu.cargar_precios_archivo, solicitud_id, filas)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        log.exception("Error cruzando precios para solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


@router.post("/constructor-apu/{solicitud_id}/enviar-analisis", tags=["Constructor APU"])
async def enviar_a_analisis(solicitud_id: int, payload: Optional[EnviarAnalisisRequest] = None,
                            user: dict = Depends(_ROL_RESIDENTE)) -> dict:
    omitir = bool(payload and payload.omitir_sin_precio)
    try:
        return await asyncio.to_thread(
            constructor_apu.enviar_a_analisis, solicitud_id, omitir, user["rol"], user["nombre"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        log.exception("Error enviando a análisis la solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="Error interno del servidor.")


class ActualizarJustificacionRequest(BaseModel):
    justificacion_tecnica: Optional[str] = None
    localizacion_obra: Optional[str] = None
    numero_acta_aprobacion: Optional[str] = None
    fecha_aprobacion_entidad: Optional[str] = None


@router.patch("/constructor-apu/{solicitud_id}/justificacion", tags=["Constructor APU"])
async def actualizar_justificacion_endpoint(
    solicitud_id: int, payload: ActualizarJustificacionRequest, user: dict = Depends(_ROL_RESIDENTE)
) -> dict:
    try:
        return await asyncio.to_thread(
            constructor_apu.actualizar_justificacion,
            solicitud_id,
            justificacion_tecnica=payload.justificacion_tecnica,
            localizacion_obra=payload.localizacion_obra,
            numero_acta_aprobacion=payload.numero_acta_aprobacion,
            fecha_aprobacion_entidad=payload.fecha_aprobacion_entidad,
        )
    except Exception:
        log.exception("Error actualizando justificación para solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="Error al actualizar datos de justificación.")


class IncorporarProyectoRequest(BaseModel):
    proyecto_id: Optional[int] = None
    numero_acta: Optional[str] = None
    fecha_aprobacion: Optional[str] = None
    justificacion: Optional[str] = None


@router.post("/constructor-apu/{solicitud_id}/incorporar", tags=["Constructor APU"])
async def incorporar_proyecto_endpoint(
    solicitud_id: int, payload: IncorporarProyectoRequest, user: dict = Depends(_ROL_RESIDENTE)
) -> dict:
    try:
        return await asyncio.to_thread(
            constructor_apu.incorporar_a_proyecto_y_banco,
            solicitud_id,
            proyecto_id=payload.proyecto_id,
            numero_acta=payload.numero_acta,
            fecha_aprobacion=payload.fecha_aprobacion,
            justificacion=payload.justificacion,
            usuario_rol=user["rol"],
            usuario_nombre=user["nombre"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        log.exception("Error incorporando APU %d al proyecto", solicitud_id)
        raise HTTPException(status_code=500, detail="Error interno al incorporar el APU.")


@router.get("/constructor-apu/{solicitud_id}/memoria-pdf", tags=["Constructor APU"])
async def descargar_memoria_pdf(solicitud_id: int, user: dict = Depends(require_role("user"))) -> Response:
    """Genera y descarga la Memoria Técnica Justificativa oficial en formato PDF."""
    from src.infrastructure.database.repositories.analisis_repository import analisis_repo
    from src.infrastructure.database.connection import execute_query
    from src.infrastructure.reporting.memoria_pdf import generar_memoria_pdf

    solicitud = await asyncio.to_thread(analisis_repo.get_solicitud, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    insumos = solicitud.get("insumos") or []
    desglose = constructor_apu.calcular_desglose_aiu(
        constructor_apu.calcular_costo_directo(insumos), proyecto_id=solicitud.get("proyecto_id"),
    )

    proyecto = None
    if solicitud.get("proyecto_id"):
        p_rows = await asyncio.to_thread(
            execute_query, "SELECT * FROM proyectos WHERE id = %s", (solicitud["proyecto_id"],)
        )
        if p_rows:
            proyecto = p_rows[0]

    try:
        pdf_bytes = await asyncio.to_thread(generar_memoria_pdf, solicitud, desglose, proyecto)
        filename = f"memoria_tecnica_apu_{solicitud_id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception:
        log.exception("Error generando PDF de memoria justificativa para solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="Error generando el archivo PDF de la memoria técnica.")


@router.get("/constructor-apu/{solicitud_id}/export-excel", tags=["Constructor APU"])
async def descargar_apu_excel(solicitud_id: int, user: dict = Depends(require_role("user"))) -> Response:
    """Genera y descarga el APU en Excel (.xlsx) con fórmulas vivas auditables."""
    from src.infrastructure.database.repositories.analisis_repository import analisis_repo
    from src.infrastructure.database.connection import execute_query
    from src.infrastructure.reporting.apu_excel_formulado import generar_apu_excel_formulado

    solicitud = await asyncio.to_thread(analisis_repo.get_solicitud, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    insumos = solicitud.get("insumos") or []
    desglose = constructor_apu.calcular_desglose_aiu(
        constructor_apu.calcular_costo_directo(insumos), proyecto_id=solicitud.get("proyecto_id"),
    )

    proyecto = None
    if solicitud.get("proyecto_id"):
        p_rows = await asyncio.to_thread(
            execute_query, "SELECT * FROM proyectos WHERE id = %s", (solicitud["proyecto_id"],)
        )
        if p_rows:
            proyecto = p_rows[0]

    try:
        excel_bytes = await asyncio.to_thread(generar_apu_excel_formulado, solicitud, desglose, proyecto)
        filename = f"apu_formulado_{solicitud_id}.xlsx"
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception:
        log.exception("Error generando Excel formulado para solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="Error generando el archivo Excel formulado.")
