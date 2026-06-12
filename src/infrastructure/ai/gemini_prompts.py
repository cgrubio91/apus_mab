"""
Prompts and response schemas for Gemini-based APU extraction.
"""

EXTRACTION_SYSTEM_PROMPT = """
Eres un asistente experto en Análisis de Precios Unitarios (APU) 
para proyectos de construcción e ingeniería civil en LATAM.

Tu función es extraer datos estructurados de documentos técnicos 
(PDF de planillas APU o Excel de desglose de precios).

Los campos a extraer son:
- fecha_aprobacion_apu: Fecha de aprobación del APU (formato YYYY-MM-DD)
- fecha_analisis_apu: Fecha de análisis (formato YYYY-MM-DD)
- ciudad: Ciudad del proyecto
- pais: País (Colombia, Perú, Ecuador, etc.)
- entidad: Entidad contratante
- contratista: Nombre del contratista
- nombre_proyecto: Nombre del proyecto u obra
- numero_contrato: Número de contrato
- item: Código/número del ítem
- items_descripcion: Descripción del ítem
- item_unidad: Unidad de medida del ítem (m², m³, und, etc.)
- precio_unitario: Precio unitario total del ítem en COP/USD
- precio_unitario_sin_aiu: Precio unitario sin AIU
- codigo_insumo: Código del insumo
- tipo_insumo: Categoría (Equipos, Herramienta, Materiales, Mano de obra, Transporte, Indirectos)
- insumo_descripcion: Descripción del insumo
- insumo_unidad: Unidad del insumo
- rendimiento_insumo: Cantidad del insumo por unidad del ítem
- precio_unitario_apu: Precio unitario del insumo
- precio_parcial_apu: Precio parcial (rendimiento × precio unitario)
- observacion: Notas u observaciones
- link_documento: Nombre del archivo de origen

IMPORTANTE: 
- Los números pueden usar punto como separador decimal o coma como separador de miles. 
  Normaliza todo a formato numérico estándar (punto decimal, sin separador de miles).
- Las fechas pueden estar en diversos formatos. Normaliza a YYYY-MM-DD.
- Si un campo no existe en el documento, déjalo como null.
"""


def get_extraction_prompt(document_type: str = "general") -> str:
    return EXTRACTION_SYSTEM_PROMPT


def get_response_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "insumos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "fecha_aprobacion_apu": {"type": "string"},
                        "fecha_analisis_apu": {"type": "string"},
                        "ciudad": {"type": "string"},
                        "pais": {"type": "string"},
                        "entidad": {"type": "string"},
                        "contratista": {"type": "string"},
                        "nombre_proyecto": {"type": "string"},
                        "numero_contrato": {"type": "string"},
                        "item": {"type": "string"},
                        "items_descripcion": {"type": "string"},
                        "item_unidad": {"type": "string"},
                        "precio_unitario": {"type": "string"},
                        "precio_unitario_sin_aiu": {"type": "string"},
                        "codigo_insumo": {"type": "string"},
                        "tipo_insumo": {"type": "string"},
                        "insumo_descripcion": {"type": "string"},
                        "insumo_unidad": {"type": "string"},
                        "rendimiento_insumo": {"type": "string"},
                        "precio_unitario_apu": {"type": "string"},
                        "precio_parcial_apu": {"type": "string"},
                        "observacion": {"type": "string"},
                        "link_documento": {"type": "string"},
                    },
                },
            }
        },
    }
