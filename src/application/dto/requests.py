from pydantic import BaseModel, Field
from typing import Optional, Any


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1500)
    telefono: str = Field(default="web-user")
    nombre: str = Field(default="Usuario Web")


class InsumoItem(BaseModel):
    codigo: Optional[str] = Field(None, description="Código del insumo")
    descripcion: str = Field(..., description="Descripción del insumo")
    unidad: Optional[str] = Field(None, description="Unidad de medida")
    cantidad: Optional[float] = Field(None, ge=0)
    precio: Optional[float] = Field(None, ge=0)
    extra: dict[str, Any] = Field(default_factory=dict)
