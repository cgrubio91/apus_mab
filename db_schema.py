INSUMO_CATEGORIES = ["Equipos", "Herramienta", "Materiales", "Mano de obra", "Transporte", "Indirectos"]

SCHEMA_STATEMENTS = [
    # ── APU records table ──────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS apus (
        id SERIAL PRIMARY KEY,
        fecha_aprobacion_apu DATE,
        fecha_analisis_apu DATE,
        ciudad VARCHAR(100),
        pais VARCHAR(100),
        entidad VARCHAR(200),
        contratista VARCHAR(200),
        nombre_proyecto VARCHAR(200),
        numero_contrato VARCHAR(100),
        item TEXT,
        items_descripcion TEXT,
        item_unidad VARCHAR(20),
        precio_unitario NUMERIC(30,10),
        precio_unitario_sin_aiu NUMERIC(30,10),
        codigo_insumo TEXT,
        tipo_insumo VARCHAR(100),
        insumo_descripcion TEXT,
        insumo_unidad VARCHAR(20),
        rendimiento_insumo NUMERIC(30,10),
        precio_unitario_apu NUMERIC(30,10),
        precio_parcial_apu NUMERIC(30,10),
        observacion TEXT,
        link_documento TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_apus_proyecto ON apus (nombre_proyecto)",
    "CREATE INDEX IF NOT EXISTS idx_apus_ciudad ON apus (ciudad)",
    "CREATE INDEX IF NOT EXISTS idx_apus_insumo ON apus (insumo_descripcion)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_apus_unique_conflict ON apus (numero_contrato, item, codigo_insumo, link_documento)",

    # ── Authorized users table ─────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        telefono VARCHAR(50) NOT NULL UNIQUE,
        nombre VARCHAR(100),
        rol VARCHAR(20) DEFAULT 'user',
        activo BOOLEAN DEFAULT true,
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_usuarios_telefono ON usuarios (telefono)",

    # ── Conversation history table ─────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS historial_conversaciones (
        id SERIAL PRIMARY KEY,
        telefono VARCHAR(50) NOT NULL,
        mensaje_usuario TEXT NOT NULL,
        sql_generado TEXT,
        respuesta_bot TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_historial_telefono ON historial_conversaciones (telefono, timestamp DESC)",

    # ── Análisis APU - Approval Workflow Tables ────────────────────
    """
    CREATE TABLE IF NOT EXISTS solicitudes_apu (
        id SERIAL PRIMARY KEY,
        link_documento TEXT,
        contratista VARCHAR(200),
        nombre_proyecto VARCHAR(200),
        fecha_solicitud DATE DEFAULT CURRENT_DATE,
        fecha_limite_respuesta DATE,
        fecha_limite_aprobacion DATE,
        estado VARCHAR(50) DEFAULT 'pendiente_analisis',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS solicitud_insumos (
        id SERIAL PRIMARY KEY,
        solicitud_id INTEGER REFERENCES solicitudes_apu(id) ON DELETE CASCADE,
        grupo_cotizacion INTEGER DEFAULT 1,
        nombre_archivo TEXT,
        item TEXT,
        items_descripcion TEXT,
        item_unidad VARCHAR(20),
        precio_unitario NUMERIC(30,10),
        codigo_insumo TEXT,
        insumo_descripcion TEXT,
        insumo_unidad VARCHAR(20),
        rendimiento_insumo NUMERIC(30,10),
        tipo_insumo VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analisis_apu (
        id SERIAL PRIMARY KEY,
        solicitud_id INTEGER REFERENCES solicitudes_apu(id) ON DELETE CASCADE UNIQUE,
        analisis_json JSONB,
        resumen TEXT,
        recomendacion VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS historial_aprobaciones (
        id SERIAL PRIMARY KEY,
        solicitud_id INTEGER REFERENCES solicitudes_apu(id) ON DELETE CASCADE,
        accion VARCHAR(50),
        responsable_rol VARCHAR(100),
        responsable_nombre VARCHAR(200),
        motivo TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS aprendizaje_rechazos (
        id SERIAL PRIMARY KEY,
        analisis_id INTEGER REFERENCES analisis_apu(id),
        motivo_rechazo TEXT,
        contexto TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # ── Migration columns (safe idempotent ALTERs) ─────────────────
    "ALTER TABLE solicitud_insumos ADD COLUMN IF NOT EXISTS grupo_cotizacion INTEGER DEFAULT 1",
    "ALTER TABLE solicitud_insumos ADD COLUMN IF NOT EXISTS nombre_archivo TEXT",
    "ALTER TABLE solicitud_insumos ALTER COLUMN item TYPE TEXT",
    "ALTER TABLE solicitud_insumos ALTER COLUMN codigo_insumo TYPE TEXT",
    'ALTER TABLE solicitud_insumos ALTER COLUMN item_unidad TYPE VARCHAR(20)',
    'ALTER TABLE solicitud_insumos ALTER COLUMN insumo_unidad TYPE VARCHAR(20)',
]


def ensure_schema():
    from db_config import execute_query
    import logging
    log = logging.getLogger("mapus.schema")
    for stmt in SCHEMA_STATEMENTS:
        try:
            execute_query(stmt, fetch=False)
        except Exception as e:
            log.warning("Schema statement warning: %s — %s", stmt[:80], e)
    log.info("Database schema verified — all tables active")
