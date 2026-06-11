"""
Análisis APU Controller
=======================
API endpoints for the APU analysis approval workflow.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional, List

from ..services.analisis_apu_service import analisis_apu_service
from ..models.analisis_apu import (
    AnalisisApuCreate,
    AprobarRequest,
    RechazarRequest,
)

log = logging.getLogger("mapus.backend.analisis")
router = APIRouter()


class ErrorResponse(BaseModel):
    detail: str


@router.post("/analisis-apu/upload", tags=["Análisis APU"])
async def upload_cotizacion(
    files: List[UploadFile] = File(...),
):
    """Upload one or more cotización files. Extracts contratista/proyecto from documents.
    Each file becomes a 'Cotización N' group."""
    try:
        grupos_insumos = []

        for idx, file in enumerate(files):
            filename = file.filename or f"archivo_{idx+1}"
            ext = filename.split(".")[-1].lower() if "." in filename else ""

            content = await file.read()
            if len(content) > 50 * 1024 * 1024:
                raise HTTPException(status_code=413, detail=f"{filename}: Archivo demasiado grande (máx 50 MB)")

            raw_insumos = []
            if ext == "pdf":
                import tempfile
                from apu_extractor.gemini_extractor import extract_apus_from_pdf_batched

                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    raw_insumos = extract_apus_from_pdf_batched(tmp_path, filename)
                finally:
                    import os
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except PermissionError:
                            pass
            elif ext in ("xlsx", "xls"):
                import tempfile
                from apu_extractor.gemini_extractor import extract_apus_from_excel

                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    raw_insumos = extract_apus_from_excel(tmp_path, filename)
                finally:
                    import os
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except PermissionError:
                            pass
            else:
                raise HTTPException(status_code=400, detail=f"{filename}: Formato no soportado. Use PDF o Excel.")

            from apu_extractor.gemini_extractor import post_process_extracted_data
            insumos = post_process_extracted_data(raw_insumos, filename)

            if insumos:
                grupos_insumos.append({
                    "grupo_cotizacion": idx + 1,
                    "nombre_archivo": filename,
                    "insumos": insumos,
                })

        if not grupos_insumos:
            raise HTTPException(status_code=400, detail="No se pudieron extraer insumos de los archivos.")

        total_insumos = sum(len(g["insumos"]) for g in grupos_insumos)
        solicitud_id = analisis_apu_service.crear_solicitud(grupos_insumos)

        return {
            "success": True,
            "solicitud_id": solicitud_id,
            "archivos_procesados": len(grupos_insumos),
            "total_insumos": total_insumos,
            "grupos": [
                {"grupo": g["grupo_cotizacion"], "archivo": g["nombre_archivo"], "insumos": len(g["insumos"])}
                for g in grupos_insumos
            ],
            "mensaje": f"Solicitud #{solicitud_id} creada con {len(grupos_insumos)} archivo(s) y {total_insumos} ítems.",
        }

    except HTTPException:
        raise
    except Exception as e:
        log.exception("Error en upload cotización")
        raise HTTPException(status_code=500, detail=f"Error procesando archivo(s): {e}")


@router.post("/analisis-apu/crear", tags=["Análisis APU"])
async def crear_solicitud_manual(payload: AnalisisApuCreate):
    """Create a solicitud manually (without file upload)."""
    try:
        grupo = {
            "grupo_cotizacion": 1,
            "nombre_archivo": payload.link_documento,
            "insumos": [i.model_dump(exclude={"id", "solicitud_id"}) for i in payload.insumos],
        }
        solicitud_id = analisis_apu_service.crear_solicitud([grupo])
        return {"success": True, "solicitud_id": solicitud_id}
    except Exception as e:
        log.exception("Error creando solicitud manual")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analisis-apu/{solicitud_id}/analizar", tags=["Análisis APU"])
async def analizar_solicitud(solicitud_id: int):
    """Run AI analysis on a solicitud, comparing with the APU bank."""
    try:
        resultado = analisis_apu_service.realizar_analisis(solicitud_id)
        return {"success": True, **resultado}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error analizando solicitud")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analisis-apu", tags=["Análisis APU"])
async def listar_solicitudes(estado: Optional[str] = None):
    """List all solicitudes, optionally filtered by estado."""
    try:
        solicitudes = analisis_apu_service.get_solicitudes(estado)
        for s in solicitudes:
            for campo in ("fecha_solicitud", "fecha_limite_respuesta", "fecha_limite_aprobacion", "created_at", "updated_at"):
                if s.get(campo) and hasattr(s[campo], "isoformat"):
                    s[campo] = s[campo].isoformat()
        return {"success": True, "data": solicitudes}
    except Exception as e:
        log.exception("Error listando solicitudes")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analisis-apu/{solicitud_id}", tags=["Análisis APU"])
async def obtener_solicitud(solicitud_id: int):
    """Get full details of a solicitud including insumos, analysis, and history."""
    try:
        solicitud = analisis_apu_service.get_solicitud(solicitud_id)
        if not solicitud:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")

        for campo in ("fecha_solicitud", "fecha_limite_respuesta", "fecha_limite_aprobacion", "created_at", "updated_at"):
            if solicitud.get(campo) and hasattr(solicitud[campo], "isoformat"):
                solicitud[campo] = solicitud[campo].isoformat()

        if solicitud.get("analisis"):
            if solicitud["analisis"].get("created_at") and hasattr(solicitud["analisis"]["created_at"], "isoformat"):
                solicitud["analisis"]["created_at"] = solicitud["analisis"]["created_at"].isoformat()

        for h in solicitud.get("historial", []):
            if h.get("created_at") and hasattr(h["created_at"], "isoformat"):
                h["created_at"] = h["created_at"].isoformat()

        return {"success": True, "data": solicitud}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Error obteniendo solicitud")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analisis-apu/{solicitud_id}/preaprobar", tags=["Análisis APU"])
async def preaprobar_apu(solicitud_id: int, payload: AprobarRequest):
    """User approves the pre-analysis. Sends to subgerente técnico."""
    try:
        resultado = analisis_apu_service.preaprobar(
            solicitud_id, payload.responsable_rol, payload.responsable_nombre
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error en preaprobación")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analisis-apu/{solicitud_id}/rechazar", tags=["Análisis APU"])
async def rechazar_apu(solicitud_id: int, payload: RechazarRequest):
    """User rejects the analysis with explanation. AI learns from this."""
    try:
        resultado = analisis_apu_service.rechazar(
            solicitud_id, payload.responsable_rol, payload.responsable_nombre, payload.motivo
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error en rechazo")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analisis-apu/{solicitud_id}/nuevas-cotizaciones", tags=["Análisis APU"])
async def nuevas_cotizaciones(solicitud_id: int):
    """Register that new quotes were received after rejection."""
    try:
        resultado = analisis_apu_service.nuevas_cotizaciones_recibidas(solicitud_id)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error registrando nuevas cotizaciones")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analisis-apu/{solicitud_id}/aprobar-subgerente", tags=["Análisis APU"])
async def aprobar_subgerente(solicitud_id: int, payload: AprobarRequest):
    """Subgerente técnico approves. Sends to legal representative."""
    try:
        resultado = analisis_apu_service.aprobar_subgerente(
            solicitud_id, payload.responsable_rol, payload.responsable_nombre
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error en aprobación de subgerente")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analisis-apu/{solicitud_id}/firmar-legal", tags=["Análisis APU"])
async def firmar_legal(solicitud_id: int, payload: AprobarRequest):
    """Professional support signs as legal representative."""
    try:
        resultado = analisis_apu_service.firmar_legal(
            solicitud_id, payload.responsable_rol, payload.responsable_nombre
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Error en firma legal")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analisis-apu/aprendizaje/rechazos", tags=["Análisis APU"])
async def obtener_aprendizaje(limit: int = 20):
    """Get rejection history for AI learning."""
    try:
        data = analisis_apu_service.get_aprendizaje_rechazos(limit)
        return {"success": True, "data": data}
    except Exception as e:
        log.exception("Error obteniendo aprendizaje")
        raise HTTPException(status_code=500, detail=str(e))
