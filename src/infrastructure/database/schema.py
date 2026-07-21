INSUMO_CATEGORIES = ["Equipos", "Herramienta", "Materiales", "Mano de obra", "Transporte", "Indirectos"]

# ──────────────────────────────────────────────
# SCHEMA: interventoría + MAPUS
# Orden: CREATE TABLEs primero, luego ALTER/INDEX
# ──────────────────────────────────────────────

SCHEMA_STATEMENTS = [

    # ── Tablas de interventoría (integración) ──

    """
    CREATE TABLE IF NOT EXISTS rol (
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(60) NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        descripcion VARCHAR(400),
        palabras_clave VARCHAR(500),
        es_sistema TINYINT(1) DEFAULT 0,
        activo TINYINT(1) DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uni_rol_codigo (codigo)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
    """,

    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        cc VARCHAR(20) NOT NULL,
        email VARCHAR(50) NOT NULL,
        password VARCHAR(300) NOT NULL,
        phone VARCHAR(20) NOT NULL,
        position VARCHAR(100) NOT NULL,
        proyecto VARCHAR(200) NOT NULL,
        agentic_workspace LONGTEXT,
        agentic_workspace_sender VARCHAR(32),
        KEY idx_user_lookup (cc, proyecto(100)),
        KEY idx_users_agentic_sender (agentic_workspace_sender)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
    """,

    """
    CREATE TABLE IF NOT EXISTS usuario_rol (
        user_id INT NOT NULL,
        rol_id INT NOT NULL,
        PRIMARY KEY (user_id),
        KEY idx_usuario_rol_rol (rol_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
    """,

    """
    CREATE TABLE IF NOT EXISTS proyectos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_proy INT NOT NULL,
        descripcion VARCHAR(500),
        presupuesto_total DECIMAL(15,2),
        id_folder VARCHAR(50) NOT NULL,
        id_folder_bim VARCHAR(50),
        pdo_current_version_id INT,
        pdo_drive_subfolder_id VARCHAR(120)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
    """,

    """
    CREATE TABLE IF NOT EXISTS item_proyecto (
        id INT AUTO_INCREMENT PRIMARY KEY,
        proyecto INT NOT NULL,
        parent_id INT,
        nivel INT NOT NULL,
        codigo VARCHAR(100) NOT NULL,
        especif_gral_raw VARCHAR(255),
        especif_part_raw VARCHAR(255),
        grupo_ajuste_raw VARCHAR(120),
        nombre TEXT NOT NULL,
        descripcion TEXT,
        unidad_medida VARCHAR(50),
        cantidad_presupuestada DECIMAL(13,2),
        valor_unitario DECIMAL(15,2),
        valor_presupuestado DECIMAL(15,2) DEFAULT 0.00,
        ai DECIMAL(12,2),
        aiu DECIMAL(12,2),
        orden INT,
        aprobado_interventoria TINYINT(1) DEFAULT 0,
        id_folder VARCHAR(100),
        start_activities TINYINT(4) DEFAULT 0,
        tipo_item ENUM('PREVISTO','NP','NPP') DEFAULT 'PREVISTO',
        estado_referencia_tecnica_id INT,
        apu_solicitud_id INT,
        aprobado_costos TINYINT(1) DEFAULT 0,
        KEY parent_id (parent_id),
        KEY idx_item_hierarchy (proyecto, parent_id),
        KEY idx_item_nivel (nivel),
        KEY idx_item_apu_solicitud (apu_solicitud_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
    """,

    # ── Tablas MAPUS ──

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

    """
    CREATE TABLE IF NOT EXISTS solicitudes_apu (
        id INT AUTO_INCREMENT PRIMARY KEY,
        link_documento TEXT,
        contratista VARCHAR(200),
        nombre_proyecto VARCHAR(200),
        proyecto_id INT,
        fecha_solicitud DATE DEFAULT (CURRENT_DATE),
        fecha_limite_respuesta DATE,
        fecha_limite_aprobacion DATE,
        estado VARCHAR(50) DEFAULT 'pendiente_analisis',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_solicitudes_proyecto (proyecto_id)
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

    # ── Índices adicionales ──

    "CREATE INDEX idx_apus_proyecto ON apus (nombre_proyecto(100))",
    "CREATE INDEX idx_apus_ciudad ON apus (ciudad(50))",
    "CREATE INDEX idx_apus_insumo ON apus (insumo_descripcion(100))",
    "CREATE UNIQUE INDEX idx_apus_unique_conflict ON apus (numero_contrato(100), item(100), codigo_insumo(100), link_documento(200))",
    "CREATE INDEX idx_historial_telefono ON historial_conversaciones (telefono, timestamp DESC)",
    "CREATE UNIQUE INDEX idx_notif_clave ON notificaciones (clave_unica)",
    "CREATE INDEX idx_notif_rol ON notificaciones (rol_destino, created_at DESC)",

    # ── Migraciones para tablas que ya existen sin las columnas de integración ──
    "ALTER TABLE solicitudes_apu ADD COLUMN proyecto_id INT NULL",
    "ALTER TABLE solicitudes_apu ADD INDEX idx_solicitudes_proyecto (proyecto_id)",
    "ALTER TABLE item_proyecto ADD COLUMN apu_solicitud_id INT NULL",
    "ALTER TABLE item_proyecto ADD COLUMN aprobado_costos TINYINT(1) DEFAULT 0",
    "ALTER TABLE item_proyecto ADD INDEX idx_item_apu_solicitud (apu_solicitud_id)",
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
    _seed_interventoria_data()
    log.info("Database schema verified — all tables active")


def _seed_interventoria_data():
    """Poblado inicial de tablas interventoría para desarrollo local.
    Los roles se sincronizan siempre (INSERT IGNORE).
    Usuarios y proyectos se siembran solo si la tabla users está vacía."""
    from src.infrastructure.database.connection import execute_query
    import logging
    log = logging.getLogger("mapus.schema.seed")

    try:
        _ = execute_query("SELECT COUNT(*) AS cnt FROM rol")
    except Exception:
        return

    log.info("Sincronizando roles...")
    try:
        execute_query(
            """INSERT IGNORE INTO rol (id, codigo, nombre, descripcion, es_sistema, activo) VALUES
               (1, 'super_admin', 'Super administrador', 'Acceso total. Gestiona permisos en cualquier proyecto.', 1, 1),
               (2, 'director', 'Director de Interventoría', 'Lidera el proyecto. Aprueba cortes/actas.', 0, 1),
               (3, 'residente', 'Residente Técnico', 'Seguimiento de obra, genera memorias.', 0, 1),
               (4, 'topografo', 'Topógrafo', 'Captura datos de campo.', 0, 1),
               (5, 'inspector', 'Inspector Técnico', 'Inspección en campo.', 0, 1),
               (6, 'calidad', 'Calidad / Laboratorios', 'Control de calidad.', 0, 1),
               (7, 'bim', 'Especialista BIM', 'Gestiona modelos BIM.', 0, 1),
               (8, 'legal', 'Revisor Legal', 'Revisión y firma legal de APUs.', 0, 1),
               (9, 'admin', 'Administrador MAPUS', 'Administrador interno del módulo APU.', 0, 1),
               (10, 'subgerente', 'Subgerente MAPUS', 'Subgerente del módulo APU.', 0, 1),
               (11, 'analista', 'Analista MAPUS', 'Analista del módulo APU.', 0, 1),
               (12, 'contraparte', 'Contraparte MAPUS', 'Contraparte del módulo APU.', 0, 1),
               (13, 'user', 'Usuario MAPUS', 'Usuario base del módulo APU.', 0, 1)""",
            fetch=False,
        )
    except Exception:
        log.exception("Error sincronizando roles")

    try:
        rows = execute_query("SELECT COUNT(*) AS cnt FROM users")
    except Exception:
        return

    if rows and rows[0].get("cnt", 0) > 0:
        log.info("Users ya tiene datos — se omite siembra de usuarios de prueba.")
        return

    log.info("Sembrando usuarios de prueba...")
    try:
        execute_query(
            """INSERT IGNORE INTO rol (id, codigo, nombre, descripcion, es_sistema, activo) VALUES
               (1, 'super_admin', 'Super administrador', 'Acceso total. Gestiona permisos en cualquier proyecto.', 1, 1),
               (2, 'director', 'Director de Interventoría', 'Lidera el proyecto. Aprueba cortes/actas.', 0, 1),
               (3, 'residente', 'Residente Técnico', 'Seguimiento de obra, genera memorias.', 0, 1),
               (4, 'topografo', 'Topógrafo', 'Captura datos de campo.', 0, 1),
               (5, 'inspector', 'Inspector Técnico', 'Inspección en campo.', 0, 1),
               (6, 'calidad', 'Calidad / Laboratorios', 'Control de calidad.', 0, 1),
               (7, 'bim', 'Especialista BIM', 'Gestiona modelos BIM.', 0, 1),
               (8, 'legal', 'Revisor Legal', 'Revisión y firma legal de APUs.', 0, 1),
               (9, 'admin', 'Administrador MAPUS', 'Administrador interno del módulo APU.', 0, 1),
               (10, 'subgerente', 'Subgerente MAPUS', 'Subgerente del módulo APU.', 0, 1),
               (11, 'analista', 'Analista MAPUS', 'Analista del módulo APU.', 0, 1),
               (12, 'contraparte', 'Contraparte MAPUS', 'Contraparte del módulo APU.', 0, 1),
               (13, 'user', 'Usuario MAPUS', 'Usuario base del módulo APU.', 0, 1)""",
            fetch=False,
        )

        pwd_hash = "$2b$12$/9BSumIps7BeQCEGZvj7W.sMXBpl9HtY5F/UYi0WFL565iHQNm5RK"

        execute_query(
            f"""INSERT IGNORE INTO users (id, name, cc, email, password, phone, position, proyecto) VALUES
               (1, 'Super Admin MAPUS', '0000000001', 'admin@mapus.local', '{pwd_hash}', '3000000001', 'Super Admin', 'LOCAL'),
               (2, 'Subgerente MAPUS', '0000000002', 'subgerente@mapus.local', '{pwd_hash}', '3000000002', 'Subgerente', 'LOCAL'),
               (3, 'Analista MAPUS', '0000000003', 'analista@mapus.local', '{pwd_hash}', '3000000003', 'Analista', 'LOCAL'),
               (4, 'Legal MAPUS', '0000000004', 'legal@mapus.local', '{pwd_hash}', '3000000004', 'Revisor Legal', 'LOCAL'),
               (5, 'Contraparte MAPUS', '0000000005', 'contraparte@mapus.local', '{pwd_hash}', '3000000005', 'Contraparte', 'LOCAL')""",
            fetch=False,
        )

        execute_query(
            """INSERT IGNORE INTO usuario_rol (user_id, rol_id) VALUES
               (1, 9),   -- admin → MAPUS admin
               (2, 10),  -- subgerente → MAPUS subgerente
               (3, 11),  -- analista → MAPUS analista
               (4, 8),   -- legal → MAPUS legal
               (5, 12)   -- contraparte → MAPUS contraparte""",
            fetch=False,
        )

        execute_query(
            """INSERT IGNORE INTO proyectos (id, id_proy, descripcion, presupuesto_total, id_folder) VALUES
               (1, 100, 'PROYECTO LOCAL PRUEBA', 1000000000.00, 'local_folder')""",
            fetch=False,
        )

        log.info("Datos de prueba sembrados correctamente.")
    except Exception:
        log.exception("Error sembrando datos de prueba interventoría")
