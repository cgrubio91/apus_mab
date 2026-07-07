INSUMO_CATEGORIES = ["Equipos", "Herramienta", "Materiales", "Mano de obra", "Transporte", "Indirectos"]

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS apus (
        id INT AUTO_INCREMENT PRIMARY KEY,
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
        precio_unitario DECIMAL(30,10),
        precio_unitario_sin_aiu DECIMAL(30,10),
        codigo_insumo TEXT,
        tipo_insumo VARCHAR(100),
        insumo_descripcion TEXT,
        insumo_unidad VARCHAR(20),
        rendimiento_insumo DECIMAL(30,10),
        precio_unitario_apu DECIMAL(30,10),
        precio_parcial_apu DECIMAL(30,10),
        observacion TEXT,
        link_documento TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX idx_apus_proyecto ON apus (nombre_proyecto(100))",
    "CREATE INDEX idx_apus_ciudad ON apus (ciudad(50))",
    "CREATE INDEX idx_apus_insumo ON apus (insumo_descripcion(100))",
    "CREATE UNIQUE INDEX idx_apus_unique_conflict ON apus (numero_contrato(100), item(100), codigo_insumo(100), link_documento(200))",

    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id INT AUTO_INCREMENT PRIMARY KEY,
        telefono VARCHAR(50) NOT NULL UNIQUE,
        nombre VARCHAR(100),
        rol VARCHAR(20) DEFAULT 'user',
        activo BOOLEAN DEFAULT true,
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        password_hash VARCHAR(255)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX idx_usuarios_telefono ON usuarios (telefono)",

    """
    CREATE TABLE IF NOT EXISTS historial_conversaciones (
        id INT AUTO_INCREMENT PRIMARY KEY,
        telefono VARCHAR(50) NOT NULL,
        mensaje_usuario TEXT NOT NULL,
        sql_generado TEXT,
        respuesta_bot TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE INDEX idx_historial_telefono ON historial_conversaciones (telefono, timestamp DESC)",

    """
    CREATE TABLE IF NOT EXISTS solicitudes_apu (
        id INT AUTO_INCREMENT PRIMARY KEY,
        link_documento TEXT,
        contratista VARCHAR(200),
        nombre_proyecto VARCHAR(200),
        fecha_solicitud DATE DEFAULT (CURRENT_DATE),
        fecha_limite_respuesta DATE,
        fecha_limite_aprobacion DATE,
        estado VARCHAR(50) DEFAULT 'pendiente_analisis',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS solicitud_insumos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        solicitud_id INTEGER,
        grupo_cotizacion INTEGER DEFAULT 1,
        nombre_archivo TEXT,
        item TEXT,
        items_descripcion TEXT,
        item_unidad VARCHAR(20),
        precio_unitario DECIMAL(30,10),
        codigo_insumo TEXT,
        insumo_descripcion TEXT,
        insumo_unidad VARCHAR(20),
        rendimiento_insumo DECIMAL(30,10),
        tipo_insumo VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (solicitud_id) REFERENCES solicitudes_apu(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS analisis_apu (
        id INT AUTO_INCREMENT PRIMARY KEY,
        solicitud_id INTEGER UNIQUE,
        analisis_json JSON,
        resumen TEXT,
        recomendacion VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (solicitud_id) REFERENCES solicitudes_apu(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS historial_aprobaciones (
        id INT AUTO_INCREMENT PRIMARY KEY,
        solicitud_id INTEGER,
        accion VARCHAR(50),
        responsable_rol VARCHAR(100),
        responsable_nombre VARCHAR(200),
        motivo TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (solicitud_id) REFERENCES solicitudes_apu(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS aprendizaje_rechazos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        analisis_id INTEGER,
        motivo_rechazo TEXT,
        contexto TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (analisis_id) REFERENCES analisis_apu(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS notificaciones (
        id INT AUTO_INCREMENT PRIMARY KEY,
        rol_destino VARCHAR(20) NOT NULL,
        titulo VARCHAR(200),
        mensaje TEXT,
        tipo VARCHAR(50) DEFAULT 'flujo',
        solicitud_id INTEGER NULL,
        clave_unica VARCHAR(150) NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "CREATE UNIQUE INDEX idx_notif_clave ON notificaciones (clave_unica)",
    "CREATE INDEX idx_notif_rol ON notificaciones (rol_destino, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS notificaciones_leidas (
        notificacion_id INT NOT NULL,
        usuario_id INT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (notificacion_id, usuario_id),
        FOREIGN KEY (notificacion_id) REFERENCES notificaciones(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id VARCHAR(64) PRIMARY KEY,
        filename TEXT,
        status VARCHAR(30),
        progress JSON,
        result LONGTEXT,
        error TEXT,
        created_at DOUBLE,
        updated_at DOUBLE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def ensure_schema():
    from src.infrastructure.database.connection import execute_query
    import logging
    log = logging.getLogger("mapus.schema")
    for stmt in SCHEMA_STATEMENTS:
        try:
            execute_query(stmt, fetch=False)
        except Exception as e:
            log.warning("Schema statement warning: %s — %s", stmt[:80], e)
    log.info("Database schema verified — all tables active")
