from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import date
from decimal import Decimal
from db_schema import INSUMO_CATEGORIES

# ==========================================================
# APU RECORD MODEL
# ==========================================================

class ApuRecord(BaseModel):
    """Representa un registro completo de Análisis de Precios Unitarios (APU)."""
    
    # str_strip_whitespace=True limpia espacios al inicio y al final automáticamente
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    id: Optional[int] = Field(None, description="Identificador único en base de datos")
    fecha_aprobacion_apu: Optional[date] = Field(None, description="Fecha de aprobación del APU")
    fecha_analisis_apu: Optional[date] = Field(None, description="Fecha de análisis/creación del APU")
    
    ciudad: str = Field(..., min_length=1, description="Ciudad donde se ejecuta la obra")
    pais: Optional[str] = Field(None, description="País de la obra")
    entidad: Optional[str] = Field(None, description="Entidad contratante")
    contratista: Optional[str] = Field(None, description="Nombre del contratista")
    nombre_proyecto: str = Field(..., min_length=1, description="Nombre del proyecto")
    numero_contrato: Optional[str] = Field(None, description="Número del contrato")
    
    item: str = Field(..., min_length=1, description="Código del ítem")
    items_descripcion: str = Field(..., min_length=1, description="Descripción del ítem")
    item_unidad: Optional[str] = Field(None, description="Unidad de medida")
    
    precio_unitario: Optional[Decimal] = Field(None, ge=0, description="Precio unitario total")
    precio_unitario_sin_aiu: Optional[Decimal] = Field(None, ge=0, description="Precio sin AIU")
    
    codigo_insumo: Optional[str] = Field(None, description="Código del insumo")
    tipo_insumo: Optional[str] = Field(None, description="Categoría del insumo")
    insumo_descripcion: Optional[str] = Field(None, description="Descripción del insumo")
    insumo_unidad: Optional[str] = Field(None, description="Unidad del insumo")
    
    rendimiento_insumo: Optional[Decimal] = Field(None, ge=0, description="Cantidad por unidad")
    precio_unitario_apu: Optional[Decimal] = Field(None, ge=0, description="Costo unitario")
    precio_parcial_apu: Optional[Decimal] = Field(None, ge=0, description="Costo parcial")
    
    observacion: Optional[str] = Field(None, description="Notas adicionales")
    
    # OPTIMIZACIÓN: Se usa str con validación flexible para evitar que rutas relativas o strings 
    # mal formateados en la base de datos rompan la carga de datos del usuario.
    link_documento: Optional[str] = Field(None, description="URL o ruta del documento de respaldo")

    @field_validator('tipo_insumo')
    @classmethod
    def validate_tipo_insumo(cls, v):
        if v is None:
            return v
        
        # Como usamos str_strip_whitespace, v ya viene sin espacios vacíos alrededor
        allowed = set(INSUMO_CATEGORIES)
        
        # Estrategia tolerante en lectura: si viene algo fuera del catálogo de la BD, 
        # lo catalogamos como 'Otros' o lo dejamos pasar con un warning en lugar de romper el backend
        if v not in allowed:
            # Si es una variación común por strings heredados, la corregimos dinámicamente
            v_clean = v.title().strip()
            if v_clean in allowed:
                return v_clean
            # Si de plano no coincide, lo dejamos pasar para no romper el GET de datos antiguos
            # pero puedes loguearlo o clasificarlo defensivamente.
            return v
        return v

    @field_validator('link_documento')
    @classmethod
    def validate_link_documento(cls, v):
        if not v:
            return None
        # Limpieza básica para asegurar que conserve un formato de URL utilizable
        v_str = str(v).strip()
        return v_str


# ==========================================================
# APU FILTERS MODEL
# ==========================================================

class ApuFilters(BaseModel):
    """Contenedor de parámetros de filtrado para consultas."""
    model_config = ConfigDict(str_strip_whitespace=True)

    nombre_proyecto: Optional[str] = None
    ciudad: Optional[str] = None
    items_descripcion: Optional[str] = None
    insumo_descripcion: Optional[str] = None
    tipo_insumo: Optional[str] = None
    contratista: Optional[str] = None
    entidad: Optional[str] = None
    codigo_insumo: Optional[str] = None
    item: Optional[str] = None
    item_unidad: Optional[str] = None
    insumo_unidad: Optional[str] = None
    pais: Optional[str] = None
    numero_contrato: Optional[str] = None


# ==========================================================
# APU RESPONSE MODELS
# ==========================================================

class ApuListResponse(BaseModel):
    """Respuesta paginada y fuertemente tipada de la lista de APU."""
    success: bool
    count: int
    total: int
    limit: int
    offset: int
    data: List[ApuRecord]