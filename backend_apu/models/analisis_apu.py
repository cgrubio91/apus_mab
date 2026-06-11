from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal


class SolicitudInsumo(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    id: Optional[int] = None
    solicitud_id: Optional[int] = None
    grupo_cotizacion: Optional[int] = 1
    nombre_archivo: Optional[str] = None
    item: Optional[str] = None
    items_descripcion: Optional[str] = None
    item_unidad: Optional[str] = None
    precio_unitario: Optional[Decimal] = None
    codigo_insumo: Optional[str] = None
    insumo_descripcion: Optional[str] = None
    insumo_unidad: Optional[str] = None
    rendimiento_insumo: Optional[Decimal] = None
    tipo_insumo: Optional[str] = None


class SolicitudApu(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    id: Optional[int] = None
    link_documento: Optional[str] = None
    contratista: Optional[str] = None
    nombre_proyecto: Optional[str] = None
    fecha_solicitud: Optional[date] = None
    fecha_limite_respuesta: Optional[date] = None
    fecha_limite_aprobacion: Optional[date] = None
    estado: Optional[str] = "pendiente_analisis"
    insumos: Optional[List[SolicitudInsumo]] = None
    historial_aprobaciones: Optional[List["HistorialAprobacion"]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AnalisisItem(BaseModel):
    item: str
    descripcion: str
    unidad: str
    precio_ofertado: float
    mejor_precio_banco: Optional[float] = None
    diferencia_precio: Optional[float] = None
    existe_en_banco: bool = False
    item_banco_encontrado: Optional[str] = None
    estructura_insumos_coincide: Optional[bool] = None
    rendimiento_coincide: Optional[bool] = None
    observaciones: Optional[str] = None
    recomendacion: str = "pendiente"


class AnalisisApu(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    id: Optional[int] = None
    solicitud_id: int
    analisis_json: Optional[str] = None
    resumen: Optional[str] = None
    recomendacion: Optional[str] = None
    items_analizados: Optional[List[AnalisisItem]] = None
    created_at: Optional[datetime] = None


class HistorialAprobacion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    id: Optional[int] = None
    solicitud_id: Optional[int] = None
    accion: str
    responsable_rol: str
    responsable_nombre: str
    motivo: Optional[str] = None
    created_at: Optional[datetime] = None


class AnalisisApuCreate(BaseModel):
    link_documento: str
    contratista: str
    nombre_proyecto: str
    insumos: List[SolicitudInsumo]


class AnalisisRequest(BaseModel):
    solicitud_id: int


class AprobarRequest(BaseModel):
    responsable_rol: str
    responsable_nombre: str


class RechazarRequest(BaseModel):
    responsable_rol: str
    responsable_nombre: str
    motivo: str
