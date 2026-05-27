from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

class ApuRecord(BaseModel):
    id: Optional[int] = None
    fecha_aprobacion_apu: Optional[date] = None
    fecha_analisis_apu: Optional[date] = None
    ciudad: str
    pais: Optional[str] = None
    entidad: Optional[str] = None
    contratista: Optional[str] = None
    nombre_proyecto: str
    numero_contrato: Optional[str] = None
    item: str
    items_descripcion: str
    item_unidad: Optional[str] = None
    precio_unitario: Optional[float] = None
    precio_unitario_sin_aiu: Optional[float] = None
    codigo_insumo: Optional[str] = None
    tipo_insumo: Optional[str] = None
    insumo_descripcion: Optional[str] = None
    insumo_unidad: Optional[str] = None
    rendimiento_insumo: Optional[float] = None
    precio_unitario_apu: Optional[float] = None
    precio_parcial_apu: Optional[float] = None
    observacion: Optional[str] = None
    link_documento: Optional[str] = None

class ApuFilters(BaseModel):
    nombre_proyecto: Optional[str] = None
    ciudad: Optional[str] = None
    items_descripcion: Optional[str] = None
    insumo_descripcion: Optional[str] = None
    tipo_insumo: Optional[str] = None
    limit: int = 50
    offset: int = 0