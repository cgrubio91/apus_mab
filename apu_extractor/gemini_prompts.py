def get_extraction_prompt(filename: str = None) -> str:
    file_info = f" del archivo '{filename}'" if filename else ""
    return f"""
    Actúa como un extractor de datos de alta precisión experto en infraestructura y Análisis de Precios Unitarios (APU).
    Extrae la información relevante de los APUs presentados en el documento{file_info}.

    INSTRUCCIONES DE EXTRACCIÓN:
    1. Crea un registro por cada INSUMO del APU (materiales, mano de obra, equipos, transportes, indirectos, etc.).
    2. Cada registro debe representar una fila de insumo asociada a su Ítem correspondiente.
    3. Si existen costos indirectos o AIU, solo inclúyelos si aparecen desagregados como insumos en el APU.
    4. Mapea la información exactamente a los campos definidos en la estructura de salida.

    REGLAS DE FORMATO INTERNO:
    - Las fechas deben venir en formato YYYY-MM-DD. Si no se especifican, pon null.
    - Los números (precios, rendimientos, parciales) deben extraerse como números válidos en JSON (floats o enteros). No agregues puntos de miles ni signos de moneda en el JSON; de eso se encargará el formateador de salida del sistema.
    - La columna ENTIDAD corresponde a la entidad contratante (ej. IDU, INVIAS, alcaldías, etc.).

    SEGURIDAD CONTRACTUAL (crucial):
    - La columna CIUDAD y PAÍS solo deben completarse si aparecen explícitamente o existe evidencia inequívoca en el documento. No inventes ni asumas información faltante.

    LIMPIEZA DE DATOS:
    1. IGNORA filas completamente vacías, filas de totales (TOTAL, SUBTOTAL, SUMA), filas de resumen o encabezados repetidos.
    2. IGNORA filas que sean solo separadores (guiones, asteriscos, etc.).
    3. Normaliza descripciones: elimina espacios múltiples, tabs, saltos de línea internos.
    4. Unifica unidades: por ejemplo "H-H", "hh", "HH" → "H-H"; "M3", "mt3" → "M3"; "und", "unidad" → "UND".
    5. Si un insumo no tiene código o descripción clara, no lo incluyas.
    6. Limpia caracteres extraños producto de OCR (corchetes sueltos, símbolos raros, etc.).

    RESPONDE EXCLUSIVAMENTE CON UN OBJETO JSON que contenga una lista bajo la clave "insumos".
    Sigue estrictamente la estructura del esquema JSON.
    """


def get_response_schema() -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "insumos": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "fecha_aprobacion_apu": {"type": "STRING", "description": "Fecha de aprobación en formato YYYY-MM-DD o null"},
                        "fecha_analisis_apu": {"type": "STRING", "description": "Fecha de análisis en formato YYYY-MM-DD o null"},
                        "ciudad": {"type": "STRING", "description": "Ciudad del proyecto"},
                        "pais": {"type": "STRING", "description": "País del proyecto"},
                        "entidad": {"type": "STRING", "description": "Entidad contratante (ej. IDU)"},
                        "contratista": {"type": "STRING", "description": "Nombre del contratista"},
                        "nombre_proyecto": {"type": "STRING", "description": "Nombre del proyecto de infraestructura"},
                        "numero_contrato": {"type": "STRING", "description": "Número de contrato"},
                        "item": {"type": "STRING", "description": "Código o número de ítem (ej. 1.1, 2.3.a)"},
                        "items_descripcion": {"type": "STRING", "description": "Descripción o nombre del ítem principal"},
                        "item_unidad": {"type": "STRING", "description": "Unidad de medida del ítem (ej. M3, M, KG)"},
                        "precio_unitario": {"type": "NUMBER", "description": "Precio unitario total del ítem con AIU"},
                        "precio_unitario_sin_aiu": {"type": "NUMBER", "description": "Precio unitario del ítem sin AIU"},
                        "codigo_insumo": {"type": "STRING", "description": "Código identificador del insumo"},
                        "tipo_insumo": {"type": "STRING", "description": "Categoría de insumo: Equipos, Herramienta, Materiales, Mano de obra, Transporte, o Indirectos"},
                        "insumo_descripcion": {"type": "STRING", "description": "Nombre detallado del insumo"},
                        "insumo_unidad": {"type": "STRING", "description": "Unidad de medida del insumo (ej. H-G, Bto, M3)"},
                        "rendimiento_insumo": {"type": "NUMBER", "description": "Rendimiento del insumo para este ítem"},
                        "precio_unitario_apu": {"type": "NUMBER", "description": "Costo unitario del insumo"},
                        "precio_parcial_apu": {"type": "NUMBER", "description": "Costo parcial calculado (rendimiento * precio unitario)"},
                        "observacion": {"type": "STRING", "description": "Cualquier observación adicional del insumo"},
                        "link_documento": {"type": "STRING", "description": "Nombre del archivo de origen"}
                    },
                    "required": ["item", "items_descripcion", "insumo_descripcion"]
                }
            }
        }
    }
