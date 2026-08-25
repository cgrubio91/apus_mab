"""
Presentation: Constructor de APU Routes

Flujo liderado por el residente: borrador → estructura sugerida por IA →
precios del contratista → análisis comparativo contra el banco.
"""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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


@router.post("/constructor-apu/{solicitud_id}/sugerir", tags=["Constructor APU"])
async def sugerir_estructura(solicitud_id: int, user: dict = Depends(_ROL_RESIDENTE)) -> dict:
    try:
        return await asyncio.to_thread(constructor_apu.sugerir_estructura, solicitud_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        log.exception("Error sugiriendo estructura para solicitud %d", solicitud_id)
        raise HTTPException(status_code=500, detail="No se pudo generar la propuesta. Intenta nuevamente.")


@router.post("/constructor-apu/{solicitud_id}/refinar", tags=["Constructor APU"])
async def refinar_propuesta(solicitud_id: int, payload: RefinarRequest, user: dict = Depends(_ROL_RESIDENTE)) -> dict:
    try:
        return await asyncio.to_thread(
            constructor_apu.refinar_propuesta, solicitud_id, payload.conversacion,
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
