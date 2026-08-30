"""
Domain: Referencia de precio externa

Representa un dato de precio traído de una fuente EXTERNA al banco propio
(SECOP II / Colombia Compra Eficiente, DANE, listas oficiales, retail...).

Es deliberadamente agnóstico a la fuente y a la granularidad:

  - granularidad="contrato": referencia a nivel de contrato/objeto (lo que
    entrega hoy el open data estructurado de SECOP: valor del contrato, objeto,
    ciudad, fecha). NO trae desglose de insumos ni rendimiento.
  - granularidad="insumo":   un insumo con su precio unitario y, si existe,
    rendimiento (extraído de documentos/APUs).
  - granularidad="material": precio de un material suelto (retail/proveedor).

Así una sola tabla y un solo flujo de ranking sirven para SECOP, DANE y
scraping de proveedores; cada adaptador solo rellena lo que su fuente ofrece.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

GRANULARIDADES = ("contrato", "insumo", "material")


class ReferenciaExterna(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    id: Optional[int] = Field(None, description="Identificador en base de datos")

    # Procedencia (trazabilidad obligatoria de todo dato externo)
    fuente: str = Field(..., min_length=1, description="Fuente del dato, ej. 'SECOP II'")
    fuente_id: Optional[str] = Field(
        None, description="Identificador del registro en la fuente (id_contrato, sku...)"
    )
    url: Optional[str] = Field(None, description="URL de respaldo/consulta del dato")
    granularidad: str = Field("contrato", description="contrato | insumo | material")

    # Descripción de lo cotizado
    descripcion: str = Field(..., min_length=1, description="Objeto/insumo/material")
    unidad: Optional[str] = Field(None, description="Unidad de medida, si aplica")
    codigo: Optional[str] = Field(None, description="Código de clasificación (ej. UNSPSC)")

    # Precio y rendimiento
    precio: Optional[Decimal] = Field(None, ge=0, description="Valor/precio en pesos")
    rendimiento: Optional[Decimal] = Field(
        None, ge=0, description="Rendimiento por unidad (solo granularidad='insumo')"
    )

    # Contexto (para el ranking: cercanía a la ciudad y recencia)
    ciudad: Optional[str] = Field(None, description="Ciudad/municipio")
    departamento: Optional[str] = Field(None, description="Departamento")
    entidad: Optional[str] = Field(None, description="Entidad contratante")
    proveedor: Optional[str] = Field(None, description="Proveedor/contratista adjudicado")
    fecha: Optional[date] = Field(None, description="Fecha del dato (firma/publicación)")

    observacion: Optional[str] = Field(None, description="Notas de ingesta")

    def clave_unica(self) -> str:
        """Clave estable para deduplicar en re-ingestas de la misma fuente."""
        return f"{self.fuente}::{self.fuente_id or self.descripcion.lower()[:180]}"
