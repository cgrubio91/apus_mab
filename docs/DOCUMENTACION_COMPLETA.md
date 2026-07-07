# MAPUS — Documentación Técnica Completa

**MAPUS** (Mab APUs) es un sistema full-stack para la gestión, extracción, consulta y análisis de **Análisis de Precios Unitarios (APU)** en proyectos de ingeniería civil. Utiliza inteligencia artificial (Google Gemini) para extraer datos desde documentos PDF y Excel, permite consultas en lenguaje natural vía chat web y WhatsApp, e implementa un flujo de aprobación multinivel con firma legal.

---

## Índice

1. [Glosario](#1-glosario)
2. [Visión General del Sistema](#2-visión-general-del-sistema)
3. [Arquitectura del Sistema](#3-arquitectura-del-sistema)
4. [Estructura del Proyecto](#4-estructura-del-proyecto)
5. [Base de Datos](#5-base-de-datos)
   - [Esquema Físico](#51-esquema-físico)
   - [Diagrama Entidad-Relación](#52-diagrama-entidad-relación)
   - [Descripción de Tablas](#53-descripción-de-tablas)
6. [Backend — FastAPI Python](#6-backend--fastapi-python)
   - [Punto de Entrada](#61-punto-de-entrada)
   - [Capa de Presentación (Routers)](#62-capa-de-presentación-routers)
   - [Capa de Aplicación (Use Cases)](#63-capa-de-aplicación-use-cases)
   - [Capa de Dominio](#64-capa-de-dominio)
   - [Capa de Infraestructura](#65-capa-de-infraestructura)
7. [Frontend — Angular](#7-frontend--angular)
8. [Scripts Utilitarios](#8-scripts-utilitarios)
9. [Flujos del Sistema](#9-flujos-del-sistema)
   - [Extracción de APUs](#91-extracción-de-apus)
   - [Chat Asistente Web](#92-chat-asistente-web)
   - [Asistente WhatsApp](#93-asistente-whatsapp)
   - [Flujo de Aprobación de APUs](#94-flujo-de-aprobación-de-apus)
   - [Consulta y Filtros](#95-consulta-y-filtros)
10. [Configuración y Despliegue](#10-configuración-y-despliegue)
11. [Guía para Desarrolladores](#11-guía-para-desarrolladores)

---

## 1. Glosario

| Término | Significado |
|---------|-------------|
| **APU** | Análisis de Precio Unitario. Desglose detallado de los insumos (materiales, mano de obra, equipos, etc.) que componen el precio de un ítem de obra. |
| **Ítem** | Cada una de las partidas o actividades dentro de un presupuesto de obra (ej: "Concreto 3000 psi", "Excavación manual"). |
| **Insumo** | Recurso individual que compone un ítem: material, equipo, herramienta, mano de obra o transporte. |
| **AIU** | Administración, Imprevistos y Utilidad. Porcentaje que se añade al costo directo de un ítem. |
| **Precio Unitario** | Precio total de un ítem de obra por unidad de medida (m³, kg, und, etc.). |
| **Precio Parcial** | Precio de un insumo individual dentro de un ítem (rendimiento × precio unitario del insumo). |
| **Rendimiento** | Cantidad de un insumo necesaria para producir una unidad del ítem. |
| **Tipo de Insumo** | Categoría del insumo: Materiales, Mano de obra, Equipos, Herramienta, Transporte, Indirectos. |
| **Solicitud de Análisis** | Petición formal para que el sistema compare precios de una cotización contra el banco de APUs. |
| **Pre-Aprobación** | Aprobación inicial realizada por un analista. |
| **Subgerente Técnico** | Rol que revisa y aprueba las pre-aprobaciones. |
| **Firma Legal** | Aprobación final que incorpora el APU al banco de datos. |
| **Cotización** | Grupo de ítems APU provenientes de un mismo archivo o proveedor. |
| **Gemini** | Modelo de lenguaje de Google usado para extracción de datos y generación de consultas SQL. |
| **Twilio** | Plataforma de comunicaciones que integra WhatsApp con el sistema. |
| **Clean Architecture** | Patrón arquitectónico que separa el software en capas: dominio, aplicación, infraestructura y presentación. |
| **Job** | Trabajo asíncrono de extracción de documentos que se ejecuta en segundo plano. |

---

## 2. Visión General del Sistema

MAPUS permite a entidades gubernamentales y empresas constructoras:

1. **Extraer** automáticamente datos de APUs desde documentos PDF y Excel usando IA.
2. **Almacenar** en una base de datos MySQL centralizada.
3. **Consultar** mediante búsqueda por texto, filtros por columna, ordenamiento y paginación.
4. **Analizar** cotizaciones comparándolas contra el banco de APUs histórico.
5. **Aprobar** APUs mediante un flujo de trabajo multinivel (analista → subgerente → legal).
6. **Conversar** en lenguaje natural vía web y WhatsApp para obtener información.

---

## 3. Arquitectura del Sistema

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        NAVEGADOR WEB (Angular 21)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │Dashboard │  │ Consulta │  │Extracción│  │   Chat   │  │ Análisis │  │
│  │  APUs    │  │   APUs   │  │  IA PDF  │  │Asistente │  │Aprobación│  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │ HTTP REST
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          NGINX (puerto 80/8080)                          │
│      Proxy reverso: /api/* → api:10000, / → static Angular              │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
┌──────────────────────────────────────────────────────────────────────────┐
│                    FASTAPI — Python 3.11 (puerto 10000)                   │
│                                                                          │
│  ┌──────────────── PRESENTACIÓN ─────────────────────────────────────┐   │
│  │  Routers: apus, chat, extractor, analisis_apu, whatsapp, auth    │   │
│  │  Middleware: CORS, logging, rate limiting (30 req/min chat)       │   │
│  │  Auth: JWT + bcrypt + jerarquía de roles                          │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                 │                                         │
│  ┌──────────────── APLICACIÓN ───────────────────────────────────────┐   │
│  │  Use Cases: chat_assistant, extract_apu, manage_analisis,        │   │
│  │             query_apus, whatsapp_assistant                        │   │
│  │  DTOs: ChatRequest, InsumoItem                                    │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                 │                                         │
│  ┌───────────────── DOMINIO ─────────────────────────────────────────┐   │
│  │  Entidades: ApuRecord, Job, SolicitudApu, AnalisisApu            │   │
│  │  Puertos (interfaces): ApuRepository, AIProvider, JobManagerPort │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                 │                                         │
│  ┌────────────── INFRAESTRUCTURA ────────────────────────────────────┐   │
│  │  DB: MySQL pool (mysql-connector) + Repository implementations      │   │
│  │  AI: Gemini API / Ollama (local) con retry+backoff               │   │
│  │  Jobs: ThreadPoolExecutor para extracción asíncrona              │   │
│  │  PDF: pypdf (texto + multimodal base64)                          │   │
│  │  Excel: pandas + openpyxl                                        │   │
│  │  SQL Validator: allowlist + blocklist + LIMIT forzado            │   │
│  └───────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────────┐
│                      Google Cloud SQL / Docker MySQL 8.0              │
│    apus · usuarios · historial_conversaciones · solicitudes_apu          │
│    solicitud_insumos · analisis_apu · historial_aprobaciones            │
│    aprendizaje_rechazos                                                   │
└──────────────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
           Google Gemini AI           Twilio WhatsApp
           (Extracción + Chat)        (Webhook + SMS API)
```

### Stack Tecnológico

| Capa | Tecnología | Versión |
|------|------------|---------|
| Frontend | Angular (standalone components) | 21.x |
| Backend | FastAPI (Clean Architecture) | 0.115.x |
| IA | Google Gemini / Ollama (local) | gemini-2.5-flash |
| Base de Datos | MySQL | 8.0 |
| WhatsApp | Twilio API | 9.x |
| PDF | pypdf | 4.x |
| Excel | openpyxl / pandas | 2.x |
| Runtime | Python | 3.11.9 |
| Contenedores | Docker + Docker Compose | — |

---

## 4. Estructura del Proyecto

```
apus_mab/
│
├── main.py                          # Entry point — arranca FastAPI
├── db_config.py                     # Wrapper de conexión BD (delega a src/)
├── db_schema.py                     # Wrapper de schema BD (delega a src/)
├── Dockerfile                       # Docker backend
├── Dockerfile.frontend              # Docker frontend (multi-stage)
├── docker-compose.yml               # mysql + api + frontend
├── nginx.conf                       # Config Nginx con proxy reverso
├── init.sql                         # Schema SQL inicial
├── Procfile                         # Despliegue Heroku
├── requirements.txt                 # Dependencias Python
├── runtime.txt                      # Versión Python
├── pyproject.toml                   # Config ruff + pytest
├── .env                             # Variables de entorno (no trackeado)
├── .env.example                     # Template de variables
│
├── src/                             # ★ CÓDIGO PRINCIPAL (Clean Architecture)
│   ├── config/                      # Configuración centralizada
│   │   └── settings.py              #   Clase Settings con pydantic-settings
│   │
│   ├── domain/                      # Capa de dominio (reglas de negocio)
│   │   ├── entities/                #   Entidades del negocio
│   │   │   ├── apu.py               #     ApuRecord, ApuFilters, ApuListResponse
│   │   │   ├── analisis.py          #     SolicitudApu, AnalisisApu, etc.
│   │   │   └── job.py               #     Job, JobStatus, JobCancelled
│   │   └── ports/                   #   Interfaces (puertos)
│   │       ├── apu_repository.py    #     Contrato para repositorio APU
│   │       ├── analisis_repository.py #   Contrato para repositorio análisis
│   │       ├── ai_provider.py       #     Contrato para proveedor IA
│   │       └── job_manager.py       #     Contrato para gestor de trabajos
│   │
│   ├── application/                 # Capa de aplicación (casos de uso)
│   │   ├── dto/                     #   Objetos de transferencia
│   │   │   └── requests.py          #     ChatRequest, InsumoItem
│   │   └── use_cases/              #   Casos de uso orquestados
│   │       ├── chat_assistant.py    #     NL → SQL → resultados → resumen
│   │       ├── whatsapp_assistant.py#     Asistente para WhatsApp
│   │       ├── extract_apu.py       #     Procesamiento de archivos
│   │       ├── manage_analisis.py   #     Flujo de aprobación
│   │       └── query_apus.py        #     Consultas y filtros
│   │
│   ├── infrastructure/              # Capa de infraestructura
│   │   ├── database/                #   Base de datos
│   │   │   ├── connection.py        #     Pool de conexiones, DBEncoder
│   │   │   ├── schema.py            #     Schema SQL (SCHEMA_STATEMENTS)
│   │   │   └── repositories/        #     Implementaciones de repositorios
│   │   │       ├── apu_repository.py    #   CRUD APU (MySQL)
│   │   │       └── analisis_repository.py # CRUD análisis y aprobaciones
│   │   ├── ai/                      #   Inteligencia Artificial
│   │   │   ├── provider.py          #     Gemini / Ollama provider
│   │   │   ├── gemini_extractor.py  #     Orquestación de extracción
│   │   │   ├── gemini_cleaners.py   #     Limpieza de datos extraídos
│   │   │   ├── gemini_prompts.py    #     Prompts y schemas JSON
│   │   │   ├── pdf_parser.py        #     Parser PDF (pypdf)
│   │   │   └── excel_parser.py      #     Parser Excel (pandas)
│   │   ├── jobs/                    #   Trabajos asíncronos
│   │   │   └── manager.py           #     JobManager (ThreadPoolExecutor)
│   │   └── sql_validator.py         #   Validador SQL (allowlist/blocklist)
│   │
│   └── presentation/                # Capa de presentación (FastAPI)
│       ├── main.py                  #   create_app() — fábrica de aplicación
│       ├── auth.py                  #   JWT, bcrypt, jerarquía de roles
│       ├── middleware.py            #   Rate limiting + logging
│       └── routers/                 #   Rutas API
│           ├── apus.py              #     /apus, /dashboard, /projects
│           ├── chat.py              #     /chat-assistant
│           ├── extractor.py         #     /extract-file, /jobs
│           ├── analisis_apu.py      #     /analisis-apu/*
│           ├── whatsapp.py          #     /whatsapp_webhook
│           └── auth.py              #     /auth/login, /auth/register
│
├── frontend/                        # ★ FRONTEND ANGULAR
│   └── src/
│       ├── main.ts                  #   Bootstrap Angular
│       ├── environments/            #   Config URL (dev/prod)
│       └── app/
│           ├── app.ts               #   Componente raíz
│           ├── app.routes.ts        #   Definiciones de rutas
│           ├── app.config.ts        #   Providers
│           ├── components/
│           │   └── sidebar/         #   Barra de navegación
│           ├── services/
│           │   ├── apu.ts           #   Servicio HTTP (todos los endpoints)
│           │   ├── auth.service.ts  #   Autenticación JWT
│           │   ├── auth.guard.ts    #   Guard de rutas
│           │   └── http.interceptor.ts # Timeout + Auth header
│           └── pages/
│               ├── login/           #   Pantalla de inicio de sesión
│               ├── dashboard-apus/  #   Dashboard con estadísticas
│               ├── consulta-apus/   #   Tabla con filtros y paginación
│               ├── chat-apus/       #   Chat asistente IA
│               ├── nuevos-apu-ia/   #   Carga y extracción de archivos
│               └── analisis-apu/    #   Flujo de aprobación
│
├── scripts/                         # Scripts de utilidad
├── tests/                           # Suite de pruebas (pytest)
└── docs/                            # Documentación
```

---

## 5. Base de Datos

### 5.1 Esquema Físico

La base de datos MySQL se compone de **8 tablas** divididas en dos grupos funcionales:

**Grupo 1 — Banco de APUs y Conversaciones:**
- `apus` — Registro principal de APUs extraídos
- `usuarios` — Usuarios del sistema
- `historial_conversaciones` — Historial de chat

**Grupo 2 — Flujo de Análisis y Aprobación:**
- `solicitudes_apu` — Solicitudes de análisis de cotizaciones
- `solicitud_insumos` — Ítems dentro de cada solicitud
- `analisis_apu` — Resultados del análisis por IA
- `historial_aprobaciones` — Bitácora del flujo de aprobación
- `aprendizaje_rechazos` — Registro de rechazos para entrenamiento

**Grupo 3 — Soporte:**
- `notificaciones` / `notificaciones_leidas` — Notificaciones web por rol y su estado de lectura por usuario
- `jobs` — Espejo persistente de los trabajos de extracción (sobrevive reinicios del servidor)

### 5.2 Diagrama Entidad-Relación

```
┌──────────────────┐       ┌────────────────────────┐
│     usuarios     │       │  historial_conversaciones│
├──────────────────┤       ├────────────────────────┤
│ id (PK) SERIAL   │       │ id (PK) SERIAL          │
│ telefono VARCHAR │──┐    │ telefono VARCHAR (FK)───┘
│ nombre VARCHAR   │  │    │ mensaje_usuario TEXT     │
│ rol VARCHAR      │  │    │ sql_generado TEXT        │
│ activo BOOLEAN   │  │    │ respuesta_bot TEXT       │
│ password_hash VC │  │    │ timestamp TIMESTAMP      │
│ fecha_registro   │  │    └────────────────────────┘
└──────────────────┘  │
                      │
┌──────────────────┐  │
│      apus       │   │
├──────────────────┤  │
│ id (PK) SERIAL   │  │
│ fecha_aprobacion │  │
│ fecha_analisis   │  │
│ ciudad VARCHAR   │  │
│ pais VARCHAR     │  │
│ entidad VARCHAR  │  │
│ contratista VC   │  │
│ nombre_proyecto  │  │
│ numero_contrato  │  │
│ item TEXT        │  │
│ items_descripcion│  │
│ item_unidad      │  │
│ precio_unitario  │  │  ┌──────────────────────┐
│ precio_unit_sin  │  │  │  aprendizaje_rechazos │
│ codigo_insumo    │  │  ├──────────────────────┤
│ tipo_insumo VC   │  │  │ id (PK) SERIAL       │
│ insumo_descrip   │  │  │ analisis_id (FK)─────┐│
│ insumo_unidad    │  │  │ motivo_rechazo TEXT   ││
│ rendimiento_ins  │  │  │ contexto TEXT         ││
│ precio_unit_apu  │  │  │ created_at TIMESTAMP  ││
│ precio_parcial   │  │  └──────────────────────┘│
│ observacion      │  │                          │
│ link_documento   │  │  ┌──────────────────────┐│
│ created_at       │  │  │    analisis_apu      ││
└──────────────────┘  │  ├──────────────────────┤│
                      │  │ id (PK) SERIAL       ││
┌──────────────────┐  │  │ solicitud_id (FK)────┼┼───┐
│ solicitudes_apu  │  │  │ analisis_json JSONB  ││   │
├──────────────────┤  │  │ resumen TEXT          ││   │
│ id (PK) SERIAL   │  │  │ recomendacion VARCHAR││   │
│ link_documento   │──┼──│ created_at TIMESTAMP  ││   │
│ contratista VC   │  │  └──────────────────────┘│   │
│ nombre_proyecto  │  │                          │   │
│ fecha_solicitud  │  │  ┌──────────────────────┐│   │
│ fecha_lim_resp   │  │  │ historial_aprobaciones││  │
│ fecha_lim_aprob  │  │  ├──────────────────────┤│  │
│ estado VARCHAR   │  │  │ id (PK) SERIAL       ││  │
│ created_at       │  │  │ solicitud_id (FK)────┼┼──┘
│ updated_at       │  │  │ accion VARCHAR       ││
└────────┬─────────┘  │  │ responsable_rol VC   ││
         │            │  │ responsable_nombre VC││
         │ 1          │  │ motivo TEXT          ││
         │            │  │ created_at TIMESTAMP  ││
         ▼ N          │  └──────────────────────┘│
┌──────────────────┐  │                          │
│ solicitud_insumos │  └──────────────────────────┘
├──────────────────┤
│ id (PK) SERIAL   │
│ solicitud_id (FK)│── FK → solicitudes_apu.id
│ grupo_cotizacion │
│ nombre_archivo   │
│ item TEXT        │
│ items_descripcion│
│ item_unidad      │
│ precio_unitario  │
│ codigo_insumo    │
│ insumo_descrip   │
│ insumo_unidad    │
│ rendimiento_ins  │
│ tipo_insumo      │
│ created_at       │
└──────────────────┘

Relaciones:
- usuarios.id  ──< historial_conversaciones.telefono (1:N)
- solicitudes_apu.id ──< solicitud_insumos.solicitud_id (1:N)
- solicitudes_apu.id ──< analisis_apu.solicitud_id (1:1)
- solicitudes_apu.id ──< historial_aprobaciones.solicitud_id (1:N)
- analisis_apu.id ──< aprendizaje_rechazos.analisis_id (1:N)
```

### 5.3 Descripción de Tablas

#### `apus` — Registro principal de APUs

Almacena cada insumo individual dentro de un ítem APU. Un mismo ítem (mismo `item` + `nombre_proyecto`) aparece en **varias filas** (una por cada insumo que lo compone).

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | `SERIAL PK` | Identificador único |
| `fecha_aprobacion_apu` | `DATE` | Fecha de aprobación del APU |
| `fecha_analisis_apu` | `DATE` | Fecha de análisis/creación |
| `ciudad` | `VARCHAR(100)` | Ciudad del proyecto |
| `pais` | `VARCHAR(100)` | País |
| `entidad` | `VARCHAR(200)` | Entidad contratante |
| `contratista` | `VARCHAR(200)` | Contratista |
| `nombre_proyecto` | `VARCHAR(200)` | Nombre del proyecto |
| `numero_contrato` | `VARCHAR(100)` | Número de contrato |
| `item` | `TEXT` | Código del ítem APU |
| `items_descripcion` | `TEXT` | Descripción del ítem |
| `item_unidad` | `VARCHAR(20)` | Unidad del ítem (m³, kg, und, etc.) |
| `precio_unitario` | `NUMERIC(30,10)` | Precio unitario **del ítem** (constante para todas las filas del mismo ítem) |
| `precio_unitario_sin_aiu` | `NUMERIC(30,10)` | Precio sin AIU |
| `codigo_insumo` | `TEXT` | Código del insumo |
| `tipo_insumo` | `VARCHAR(100)` | Categoría: Materiales, Mano de obra, Equipos, Herramienta, Transporte, Indirectos |
| `insumo_descripcion` | `TEXT` | Descripción del insumo |
| `insumo_unidad` | `VARCHAR(20)` | Unidad del insumo |
| `rendimiento_insumo` | `NUMERIC(30,10)` | Cantidad del insumo por unidad del ítem |
| `precio_unitario_apu` | `NUMERIC(30,10)` | Precio unitario del insumo |
| `precio_parcial_apu` | `NUMERIC(30,10)` | Precio parcial (rendimiento × precio unitario) |
| `observacion` | `TEXT` | Notas adicionales |
| `link_documento` | `TEXT` | Archivo/documento de origen |
| `created_at` | `TIMESTAMP` | Fecha de inserción |

**Índices:**
- `idx_apus_proyecto` sobre `nombre_proyecto`
- `idx_apus_ciudad` sobre `ciudad`
- `idx_apus_insumo` sobre `insumo_descripcion`
- `idx_apus_unique_conflict` (UNIQUE) sobre `(numero_contrato, item, codigo_insumo, link_documento)` — evita duplicados

#### `usuarios` — Usuarios del sistema

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | `SERIAL PK` | Identificador único |
| `telefono` | `VARCHAR(50) UNIQUE` | Número de teléfono (login) |
| `nombre` | `VARCHAR(100)` | Nombre del usuario |
| `rol` | `VARCHAR(20)` | Rol: `admin`, `subgerente`, `legal`, `analista`, `contraparte`, `user` |
| `activo` | `BOOLEAN` | Si está activo |
| `password_hash` | `VARCHAR(255)` | Hash bcrypt de la contraseña |
| `fecha_registro` | `TIMESTAMP` | Fecha de registro |

**Jerarquía de roles** (nivel numérico para autorización):
- `admin` = 100
- `subgerente` = 80
- `legal` = 60
- `analista` = 40
- `contraparte` = 20
- `user` = 10

#### `historial_conversaciones` — Historial de chat

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | `SERIAL PK` | Identificador único |
| `telefono` | `VARCHAR(50)` | Número de teléfono del usuario |
| `mensaje_usuario` | `TEXT` | Mensaje enviado por el usuario |
| `sql_generado` | `TEXT` | Consulta SQL generada por la IA |
| `respuesta_bot` | `TEXT` | Respuesta del asistente |
| `timestamp` | `TIMESTAMP` | Fecha y hora del mensaje |

#### `solicitudes_apu` — Solicitudes de análisis

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | `SERIAL PK` | Identificador único |
| `link_documento` | `TEXT` | Documentos asociados |
| `contratista` | `VARCHAR(200)` | Contratista que cotiza |
| `nombre_proyecto` | `VARCHAR(200)` | Proyecto asociado |
| `fecha_solicitud` | `DATE` | Fecha de creación |
| `fecha_limite_respuesta` | `DATE` | Plazo para nuevas cotizaciones |
| `fecha_limite_aprobacion` | `DATE` | Plazo para aprobar |
| `estado` | `VARCHAR(50)` | Estado actual del flujo |
| `created_at` | `TIMESTAMP` | Fecha de creación |
| `updated_at` | `TIMESTAMP` | Última actualización |

**Estados del flujo de aprobación:**
```
pendiente_analisis → analizado → preaprobado → aprobado_subgerente → aprobado_legal
                                        ↘ rechazado → nuevas_cotizaciones → analizado (ciclo)
```

#### `solicitud_insumos` — Ítems de cada solicitud

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | `SERIAL PK` | Identificador único |
| `solicitud_id` | `INTEGER FK` | Referencia a `solicitudes_apu.id` |
| `grupo_cotizacion` | `INTEGER` | Grupo/cotización al que pertenece (1, 2, 3...) |
| `nombre_archivo` | `TEXT` | Archivo de origen del insumo |
| `item` | `TEXT` | Código del ítem |
| `items_descripcion` | `TEXT` | Descripción del ítem |
| `item_unidad` | `VARCHAR(20)` | Unidad del ítem |
| `precio_unitario` | `NUMERIC(30,10)` | Precio ofertado |
| `codigo_insumo` | `TEXT` | Código del insumo |
| `insumo_descripcion` | `TEXT` | Descripción del insumo |
| `insumo_unidad` | `VARCHAR(20)` | Unidad del insumo |
| `rendimiento_insumo` | `NUMERIC(30,10)` | Rendimiento |
| `tipo_insumo` | `VARCHAR(100)` | Tipo de insumo |
| `created_at` | `TIMESTAMP` | Fecha de creación |

#### `analisis_apu` — Resultados del análisis IA

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | `SERIAL PK` | Identificador único |
| `solicitud_id` | `INTEGER FK UNIQUE` | Referencia a `solicitudes_apu.id` (1:1) |
| `analisis_json` | `JSONB` | Resultado completo del análisis en JSON |
| `resumen` | `TEXT` | Resumen ejecutivo generado por IA |
| `recomendacion` | `VARCHAR(50)` | Recomendación: `aprobar`, `rechazar`, `revisar` |
| `created_at` | `TIMESTAMP` | Fecha del análisis |

#### `historial_aprobaciones` — Bitácora de aprobaciones

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | `SERIAL PK` | Identificador único |
| `solicitud_id` | `INTEGER FK` | Referencia a `solicitudes_apu.id` |
| `accion` | `VARCHAR(50)` | Acción realizada (preaprobado, rechazado, etc.) |
| `responsable_rol` | `VARCHAR(100)` | Rol del responsable |
| `responsable_nombre` | `VARCHAR(200)` | Nombre del responsable |
| `motivo` | `TEXT` | Motivo (obligatorio para rechazos) |
| `created_at` | `TIMESTAMP` | Fecha de la acción |

#### `aprendizaje_rechazos` — Aprendizaje de rechazos

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | `SERIAL PK` | Identificador único |
| `analisis_id` | `INTEGER FK` | Referencia a `analisis_apu.id` |
| `motivo_rechazo` | `TEXT` | Motivo del rechazo |
| `contexto` | `TEXT` | Contexto (quién rechazó, por qué) |
| `created_at` | `TIMESTAMP` | Fecha del registro |

---

## 6. Backend — FastAPI Python

### 6.1 Punto de Entrada

**Archivo:** `main.py`

```python
# main.py — Inicializa logging, importa app desde src/
from src.presentation.main import app

if __name__ == "__main__":
    uvicorn.run("src.presentation.main:app", host="0.0.0.0", port=port)
```

**Archivo raíz:** `src/presentation/main.py` — Fábrica de aplicación FastAPI
- Configura CORS middleware
- Configura rate limiting + logging middleware
- Monta routers en `/api/v1` (canónico) y `/api` (legacy)
- Ejecuta `ensure_schema()` al inicio (lifespan)
- Endpoints: `GET /`, `GET /health`

### 6.2 Capa de Presentación (Routers)

#### `src/presentation/routers/apus.py`
**Propósito:** Endpoints de consulta al banco de APUs.

| Ruta | Método | Función |
|------|--------|---------|
| `/apus` | GET | Lista APUs con filtros, búsqueda, orden y paginación |
| `/apus/filter-options` | GET | Opciones de filtro para el frontend |
| `/apus/export` | GET | Exporta el banco (con filtros) a Excel o CSV (`?formato=xlsx|csv`, máx 10.000 filas) |
| `/apus/historico-precios` | GET | Evolución mensual del precio de un insumo (avg/min/max) — `?insumo=&ciudad=&nombre_proyecto=` |
| `/dashboard` | GET | Estadísticas del dashboard |
| `/projects` | GET | Lista de proyectos únicos |
| `/projects` | DELETE | Elimina un proyecto completo |

**Filtros disponibles:** nombre_proyecto, ciudad, items_descripcion, insumo_descripcion, tipo_insumo, contratista, entidad, codigo_insumo, item, item_unidad, insumo_unidad, pais, numero_contrato.

#### `src/presentation/routers/chat.py`
**Propósito:** Endpoint del chat asistente web.

| Ruta | Método | Función |
|------|--------|---------|
| `/chat-assistant` | POST | Lenguaje natural → SQL → resultados → respuesta |

**Flujo:** Recibe `{message, telefono, nombre}`, orquesta `process_chat_message()` y retorna `{reply, sql_query, results, stages, cached, suggested_followups}`.

#### `src/presentation/routers/extractor.py`
**Propósito:** Endpoints para extracción de APUs desde archivos.

| Ruta | Método | Función |
|------|--------|---------|
| `/extract-file` | POST | Carga archivo, inicia extracción asíncrona |
| `/extract-file-async` | POST | Versión async con stream de progreso |
| `/jobs` | GET | Lista de trabajos recientes |
| `/jobs/{job_id}` | GET | Estado de un trabajo |
| `/jobs/{job_id}/stream` | GET | SSE stream de progreso |
| `/save-extracted` | POST | Guarda datos extraídos en BD (stream NDJSON) |

**Formatos soportados:** PDF, XLSX, XLS. Tamaño máximo: 50 MB.

#### `src/presentation/routers/analisis_apu.py`
**Propósito:** Flujo completo de análisis y aprobación.

| Ruta | Método | Función |
|------|--------|---------|
| `/analisis-apu/upload` | POST | Sube archivos y crea solicitud |
| `/analisis-apu/crear` | POST | Crea solicitud manualmente |
| `/analisis-apu/{id}/analizar` | POST | Ejecuta análisis IA |
| `/analisis-apu/{id}/preaprobar` | POST | Pre-aprueba (rol: analista) |
| `/analisis-apu/{id}/rechazar` | POST | Rechaza con motivo |
| `/analisis-apu/{id}/nuevas-cotizaciones` | POST | Registra nuevas cotizaciones |
| `/analisis-apu/{id}/aprobar-subgerente` | POST | Aprueba subgerente (rol: subgerente) |
| `/analisis-apu/{id}/firmar-legal` | POST | Firma legal (rol: legal) |
| `/analisis-apu` | GET | Lista solicitudes (filtro por estado) |
| `/analisis-apu/{id}` | GET | Detalle de solicitud |
| `/analisis-apu/{id}/export` | GET | Exporta el análisis comparativo a Excel |
| `/analisis-apu/aprendizaje/rechazos` | GET | Historial de aprendizaje |

> El análisis IA (`realizar_analisis`) inyecta en su prompt los motivos históricos de `aprendizaje_rechazos`, de modo que los criterios de rechazo de los revisores humanos se aplican a cotizaciones futuras.

#### `src/presentation/routers/notificaciones.py`
**Propósito:** Notificaciones web dirigidas por rol. Cada transición del flujo de aprobación crea una notificación para el rol del siguiente paso (analizado→analista, preaprobado→subgerente, aprobado_subgerente→legal, rechazado→contraparte, firmado→analista). Los `admin` ven todas. Los recordatorios de `fecha_limite_aprobacion` (próxima a vencer o vencida) se generan al consultar, deduplicados por día.

| Ruta | Método | Función |
|------|--------|---------|
| `/notificaciones` | GET | Notificaciones del rol del usuario + conteo de no leídas |
| `/notificaciones/{id}/leer` | POST | Marca una notificación como leída (por usuario) |
| `/notificaciones/leer-todas` | POST | Marca todas como leídas |

#### `src/presentation/routers/whatsapp.py`
**Propósito:** Webhook de Twilio para WhatsApp.

| Ruta | Método | Función |
|------|--------|---------|
| `/whatsapp_webhook` | POST | Recibe mensajes WhatsApp |

**Flujo:** Valida firma Twilio → verifica usuario autorizado → genera SQL → valida → ejecuta → genera respuesta → envía vía Twilio API.

#### `src/presentation/routers/auth.py`
**Propósito:** Autenticación de usuarios.

| Ruta | Método | Función |
|------|--------|---------|
| `/auth/login` | POST | Login con teléfono + contraseña (público) |
| `/auth/register` | POST | Registro público — siempre crea usuarios con rol `user` |
| `/auth/users` | GET | Lista usuarios (solo `admin`) |
| `/auth/users` | POST | Crea usuario con rol arbitrario (solo `admin`) |
| `/auth/users/{id}` | PATCH | Cambia rol o activa/desactiva usuario (solo `admin`) |

> **Nota de seguridad:** todos los routers de negocio (`/apus`, `/extract-file`, `/chat-assistant`, `/analisis-apu`, `/jobs`) requieren JWT. El SSE de jobs acepta el token por query param (`?token=`) porque EventSource no permite headers. Solo `/auth/login`, `/auth/register`, `/`, `/health` y `/whatsapp_webhook` (validado por firma Twilio) son públicos.

#### `src/presentation/auth.py`
**Propósito:** Utilidades de autenticación.
- `hash_password()` / `verify_password()` — bcrypt
- `create_access_token()` / `verify_token()` — JWT
- `get_current_user()` / `get_optional_user()` — Dependencias FastAPI
- `require_role(min_role)` — Decorador de autorización por jerarquía de roles

#### `src/presentation/middleware.py`
**Propósito:** Middleware de logging y rate limiting.
- **Rate limiting:** 30 solicitudes por minuto por IP para `/chat-assistant`
- **Logging:** Registra método, ruta, código de estado y tiempo de respuesta

### 6.3 Capa de Aplicación (Use Cases)

#### `src/application/use_cases/chat_assistant.py`
**Propósito:** Pipeline completo: lenguaje natural → SQL → ejecución → respuesta.

**Flujo:**
1. Obtiene historial conversacional del usuario (últimos 4 mensajes)
2. Verifica caché semántico (TTL 5 min, máx 500 entradas)
3. Construye prompt con contexto y envía a Gemini
4. Valida SQL con `sql_validator.py`
5. Ejecuta consulta contra MySQL
6. Genera respuesta con formato (tablas HTML, gráficos, sugerencias)
7. Guarda en `historial_conversaciones`
8. Retorna respuesta con metadatos (stages, SQL, followups)

**Características clave:**
- Caché LRU con expiración por tiempo
- Contexto multi-turno (refinamiento de consultas)
- Etapas con medición de tiempo (stages)
- Formateo de números con separadores de miles
- Preguntas de seguimiento sugeridas
- Límite de 20 registros por consulta

#### `src/application/use_cases/whatsapp_assistant.py`
**Propósito:** Versión simplificada del chat para WhatsApp.
- Sin caché
- Respuestas más cortas (máx 60 caracteres/ línea, 15 resultados)
- Sin tablas HTML (usa formato texto plano con `|`)
- Validación de usuario contra tabla `usuarios`
- Historial de últimos 5 mensajes

#### `src/application/use_cases/extract_apu.py`
**Propósito:** Orquestación de extracción de archivos.

**Dos modos de operación:**
1. `process_file()` — Síncrono con callback de progreso
2. `run_extraction()` — Asíncrono para JobManager

Delega en `gemini_extractor.py` para la extracción y post-procesamiento.

#### `src/application/use_cases/manage_analisis.py`
**Propósito:** Flujo de análisis y aprobación de APUs.

**Funciones:**
- `crear_solicitud()` — Crea solicitud a partir de grupos de insumos
- `get_solicitudes()` / `get_solicitud()` — Consulta solicitudes
- `realizar_analisis()` — Analiza cada ítem contra el banco de APUs usando IA
- `preaprobar()` — Transición a estado "preaprobado"
- `rechazar()` — Rechaza con motivo, solicita nuevas cotizaciones
- `nuevas_cotizaciones_recibidas()` — Reactiva el análisis
- `aprobar_subgerente()` / `firmar_legal()` — Siguientes niveles

**Análisis de cada ítem:** Busca en el banco de APUs por palabras clave de la descripción → compara precios → IA evalúa estructura y rendimiento → genera recomendación (aprobar/rechazar/revisar).

#### `src/application/use_cases/query_apus.py`
**Propósito:** Fachada para consultas al banco de APUs.
- `get_apus()` — Filtros, orden, paginación, búsqueda global
- `get_filter_options()` — Valores distintos para filtros
- `get_dashboard_stats()` — Métricas agregadas
- `get_unique_projects()` — Proyectos disponibles
- `delete_project()` — Eliminación de proyectos
- `save_extracted()` — Inserción en streaming

### 6.4 Capa de Dominio

#### Entidades (`src/domain/entities/`)

| Archivo | Clases | Propósito |
|---------|--------|-----------|
| `apu.py` | `ApuRecord`, `ApuFilters`, `ApuListResponse` | Modelos de datos APU con validación Pydantic |
| `analisis.py` | `SolicitudInsumo`, `SolicitudApu`, `AnalisisItem`, `AnalisisApu`, `HistorialAprobacion`, `AnalisisApuCreate`, `AprobarRequest`, `RechazarRequest` | Modelos del flujo de análisis |
| `job.py` | `Job`, `JobStatus`, `JobCancelled` | Modelos para trabajos asíncronos |

**Categorías de insumo válidas:** `Equipos`, `Herramienta`, `Materiales`, `Mano de obra`, `Transporte`, `Indirectos`.

#### Puertos (`src/domain/ports/`)

| Archivo | Interfaz | Métodos principales |
|---------|----------|-------------------|
| `apu_repository.py` | `ApuRepository` | `get_apus()`, `insert_apus_batch()`, `delete_project_apus()`, etc. |
| `analisis_repository.py` | `AnalisisRepository` | `crear_solicitud()`, `get_solicitud()`, `guardar_analisis()`, etc. |
| `ai_provider.py` | `AIProvider` | `generate_text()`, `extract_structured()`, `extract_from_pdf_multimodal()` |
| `job_manager.py` | `JobManagerPort` | `create_job()`, `submit()`, `get_job()`, `cancel_job()`, etc. |

### 6.5 Capa de Infraestructura

#### Base de Datos (`src/infrastructure/database/`)

**`connection.py`** — Pool de conexiones MySQL:
- `ThreadedConnectionPool` (min=1, max=10 por defecto)
- `PoolConnection` — Context manager que retorna conexiones al pool
- `DBEncoder` — Serializa `datetime`/`Decimal` a JSON
- `execute_query()` — Función genérica de consulta
- Soporte para Cloud SQL (Unix socket) vía `CLOUD_SQL_CONNECTION_NAME`

**`schema.py`** — Schema centralizado:
- `SCHEMA_STATEMENTS` — Lista de DDL para crear todas las tablas e índices
- `ensure_schema()` — Ejecuta los DDL al inicio del servidor
- Migraciones: ADD COLUMN con `IF NOT EXISTS`

**`repositories/apu_repository.py`** — Implementación de `ApuRepository`:
- Inserción por lotes con `executemany()` (mysql-connector)
- Fallback fila por fila con `ON CONFLICT DO NOTHING`
- Streaming de inserción (generador que emite progreso cada 200 registros)
- Normalización de `tipo_insumo` (mapea variantes como "equipo" → "Equipos")
- Consultas con filtros dinámicos y ordenamiento seguro (whitelist de columnas)
- Límite máximo de 500 registros

**`repositories/analisis_repository.py`** — Implementación de `AnalisisRepository`:
- CRUD completo para solicitudes, insumos, análisis, historial, aprendizaje
- Búsqueda en banco de APUs por palabras clave (hasta 5 palabras, mínimo 4 caracteres)
- Comparación entre grupos de cotización para identificar la mejor opción

#### Inteligencia Artificial (`src/infrastructure/ai/`)

**`provider.py`** — Proveedor abstracto de IA:
- Soporte para **Gemini** (API REST) y **Ollama** (local)
- 3 reintentos con backoff exponencial (2^n segundos)
- Reparación de JSON malformado (arrays truncados, comas finales, llaves faltantes)
- Extracción estructurada con `response_mime_type: application/json` + schema
- Extracción multimodal: envía PDF como base64 + prompt

**`gemini_extractor.py`** — Orquestador de extracción de documentos:
- **PDF batcheado:** Divide PDF en lotes de 15 páginas, envía cada lote a Gemini multimodal. Si falla, reintenta con texto plano.
- **Excel batcheado:** Parsea con pandas, divide en lotes de 80K caracteres.
- **Post-procesamiento:** Limpieza de fechas, normalización de números latinos, asignación de `link_documento`.

**`gemini_cleaners.py`** — Funciones de limpieza:
- `format_latin_number()` — Convierte "$1.234,56" → 1234.56
- `format_date()` — Normaliza múltiples formatos de fecha a YYYY-MM-DD
- `clean_text_field()` — Limpia espacios, normaliza unicode

**`gemini_prompts.py`** — Prompts y schemas:
- `get_extraction_prompt()` — Prompt detallado para extracción de APUs
- `get_response_schema()` — Schema JSON estructurado para respuesta de Gemini

**`pdf_parser.py`** — Utilidades PDF:
- `extract_text_from_pdf()` — Extrae texto plano
- `get_pdf_base64()` — Codifica PDF a base64
- `split_pdf_to_base64_batches()` — Divide PDF en lotes de N páginas

**`excel_parser.py`** — Utilidades Excel:
- `extract_text_from_excel()` — Parsea todas las hojas a texto
- `extract_text_from_excel_batched()` — Divide en lotes por tamaño de caracteres

#### Trabajos Asíncronos (`src/infrastructure/jobs/manager.py`)

**JobManager** — Gestor de trabajos en segundo plano:
- `ThreadPoolExecutor` con máximo 2 workers concurrentes
- Jobs expiran después de 2 horas (TTL)
- Seguimiento de progreso con versionado para SSE
- Operaciones thread-safe con `threading.RLock`
- Estados: `QUEUED → EXTRACTING → POST_PROCESSING → DONE / ERROR / CANCELLED`
- Soporte para cancelación de trabajos

#### Validador SQL (`src/infrastructure/sql_validator.py`)

**`validate_readonly_query()`** — Validador de seguridad:
- **Lista blanca:** Solo tabla `apus` (más CTEs)
- **Bloqueo:** DROP, TRUNCATE, DELETE, INSERT, UPDATE, ALTER, CREATE, EXECUTE, GRANT, REVOKE, COPY, VACUUM, MERGE, etc.
- **Funciones peligrosas:** pg_sleep, pg_read_file, current_setting, etc.
- **Protecciones:** No SELECT *, no multi-statement, LIMIT ≤ 20 forzado
- **Dos modos:** sqlparse (si está instalado) o regex (fallback)
- **Normalización de acentos** en strings ILIKE

---

## 7. Frontend — Angular

### 7.1 Estructura de Páginas

| Ruta | Componente | Descripción |
|------|------------|-------------|
| `/login` | `Login` | Inicio de sesión con teléfono + contraseña |
| `/dashboard-apus` | `DashboardApus` | Tarjetas con métricas: total APUs, proyectos, ciudades, precisión IA |
| `/consulta-apus` | `ConsultaApus` | Tabla de 22 columnas con filtros por columna, búsqueda global, ordenamiento y paginación |
| `/chat-apus` | `ChatApus` | Interfaz conversacional con historial, gráficos de barras, sugerencias |
| `/nuevos-apu-ia` | `NuevosApuIa` | Carga drag & drop de archivos, extracción vía IA, revisión y guardado |
| `/analisis-apu` | `AnalisisApu` | Flujo completo de aprobación con subida, análisis, preaprobación, rechazo, firma y exportación a Excel |
| `/historico-precios` | `HistoricoPrecios` | Evolución mensual del precio de un insumo con gráfico de barras, filtros por ciudad/proyecto |
| `/usuarios` | `Usuarios` | Gestión de usuarios (solo `admin`): crear, cambiar rol, activar/desactivar |

Además, el **sidebar** incluye una campana de notificaciones 🔔 con badge de no leídas: `NotificacionesService` consulta `/notificaciones` cada 60 s, muestra el panel por rol y dispara notificaciones del navegador (Notification API) para las nuevas.

### 7.2 Servicios

| Servicio | Archivo | Propósito |
|----------|---------|-----------|
| `ApuService` | `apu.ts` | Cliente HTTP para todos los endpoints de la API |
| `AuthService` | `auth.service.ts` | Login/logout JWT, almacenamiento en localStorage |
| `AuthGuard` | `auth.guard.ts` | Protección de rutas |
| `ExtendedTimeoutInterceptor` | `http.interceptor.ts` | Timeout de 2h para extracción, 30s para lo demás; añade token JWT |

### 7.3 Características Destacadas

- **Streaming de progreso:** El componente `NuevosApuIa` usa `streamJobProgress()` para consultar `GET /api/jobs/{id}` cada 2s mientras el backend procesa.
- **Guardado con NDJSON:** `saveExtractedStreaming()` usa Fetch API con `ReadableStream` para leer progreso del backend.
- **Filtros tipo Excel:** El componente `ConsultaApus` implementa menús desplegables por columna con búsqueda y selección.
- **Gráficos de barras:** El chat genera gráficos inline para datos numéricos.
- **Caché de chat:** Guarda historial en `sessionStorage`.
- **Seguridad:** Sidebar muestra usuario actual y rol; las rutas protegidas redirigen a `/login` si no hay token.

---

## 8. Scripts Utilitarios

| Script | Propósito |
|--------|-----------|
| `scripts/load_apus_csv.py` | Carga datos APU desde un archivo CSV a la base de datos con limpieza y validación. Inserta en lotes de 1000 registros. |
| `scripts/load_users.py` | Carga usuarios desde `usuarios.csv` a la tabla `usuarios`. Detecta duplicados y actualiza. |
| `scripts/create_user.py` | Crea un usuario administrador hardcodeado directamente en la BD (útil para desarrollo). |
| `scripts/explore_database.py` | Menú interactivo para explorar todas las tablas: ver estructura, contenido, exportar a JSON. |
| `scripts/limpiar_db.py` | Ejecuta `TRUNCATE apus RESTART IDENTITY CASCADE` para limpiar la tabla principal. |
| `scripts/ajuste_tabla.py` | Ajusta columnas numéricas a `NUMERIC(30,10)` para soportar valores grandes. |
| `scripts/debug_apus_request.py` | Script simple para depurar la respuesta del endpoint `/api/apus`. |
| `scripts/test_whatsapp_flow.py` | Prueba el webhook WhatsApp con usuarios autorizados y no autorizados. |

---

## 9. Flujos del Sistema

### 9.1 Extracción de APUs

```
Usuario                    Frontend                    Backend                     Gemini AI               MySQL
   │                          │                          │                          │                       │
   │  Selecciona PDF/Excel    │                          │                          │                       │
   ├─────────────────────────►│                          │                          │                       │
   │                          │  POST /extract-file      │                          │                       │
   │                          ├─────────────────────────►│                          │                       │
   │                          │   {job_id}               │                          │                       │
   │                          │◄─────────────────────────┤                          │                       │
   │                          │                          │  Crea Job (QUEUED)       │                       │
   │                          │                          │  ThreadPool ejecuta:     │                       │
   │                          │                          │    │                     │                       │
   │                          │                          │    ├─ Job (EXTRACTING)    │                       │
   │                          │                          │    │                     │                       │
   │                          │                          │    ├─ Si PDF:            │                       │
   │                          │                          │    │  split en lotes     │                       │
   │                          │                          │    │  de 15 páginas       │                       │
   │                          │                          │    │                     │                       │
   │                          │                          │    │  POST generateContent│                       │
   │                          │                          │    ├────────────────────►│                       │
   │                          │                          │    │  JSON estructurado   │                       │
   │                          │                          │    │◄────────────────────┤                       │
   │                          │                          │    │                     │                       │
   │                          │                          │    ├─ Post-procesamiento  │                       │
   │                          │                          │    │  (cleaners)          │                       │
   │                          │                          │    │                     │                       │
   │                          │                          │    ├─ Job (DONE)          │                       │
   │                          │                          │    │  {result}           │                       │
   │                          │                          │    │                     │                       │
   │  Poll cada 2s            │                          │    │                     │                       │
   │◄────────── GET /jobs/{id}├───────►                  │    │                     │                       │
   │───────────────►          │◄─────── {status:DONE}    │    │                     │                       │
   │                          │                          │    │                     │                       │
   │  Revisa datos            │                          │    │                     │                       │
   │  y hace clic "Guardar"   │                          │    │                     │                       │
   ├─────────────────────────►│                          │    │                     │                       │
   │                          │  POST /save-extracted    │    │                     │                       │
   │                          ├─────────────────────────►├────┘                     │                       │
   │                          │                          │  INSERT apus             │                       │
   │                          │  NDJSON progreso         ├─────────────────────────────────────────►        │
   │                          │◄─────────────────────────┤                          │                       │
   │  Barra de progreso       │                          │                          │                       │
   │◄─────────────────────────┤                          │                          │                       │
```

### 9.2 Chat Asistente Web

```
Usuario           Frontend              Backend                    Gemini AI              MySQL
  │                   │                    │                          │                      │
  │ "muéstrame los    │                    │                          │                      │
  │  precios de       │                    │                          │                      │
  │  concretos en     │                    │                          │                      │
  │  Bogotá"          │                    │                          │                      │
  ├──────────────────►│                    │                          │                      │
  │                   │ POST /chat-assistant                          │                      │
  │                   ├───────────────────►│                          │                      │
  │                   │                    │ 1. Obtiene historial     │                      │
  │                   │                    │    del usuario           │                      │
  │                   │                    ├─────────────────────────────────────────►       │
  │                   │                    │◄──────────────────────────────────────────┤      │
  │                   │                    │                          │                      │
  │                   │                    │ 2. Verifica caché        │                      │
  │                   │                    │    (miss)                │                      │
  │                   │                    │                          │                      │
  │                   │                    │ 3. Prompt → Gemini       │                      │
  │                   │                    ├─────────────────────────►│                      │
  │                   │                    │ "SELECT DISTINCT ON...   │                      │
  │                   │                    │  FROM apus WHERE ..."    │                      │
  │                   │                    │◄─────────────────────────┤                      │
  │                   │                    │                          │                      │
  │                   │                    │ 4. Valida SQL            │                      │
  │                   │                    │    (sql_validator.py)    │                      │
  │                   │                    │                          │                      │
  │                   │                    │ 5. Ejecuta consulta      │                      │
  │                   │                    ├─────────────────────────────────────────►       │
  │                   │                    │◄──────────────────────────────────────────┤      │
  │                   │                    │                          │                      │
  │                   │                    │ 6. Prompt → Gemini       │                      │
  │                   │                    │    (resumen + formato)   │                      │
  │                   │                    ├─────────────────────────►│                      │
  │                   │                    │ "En Bogotá hay 3...      │                      │
  │                   │                    │  $ 1,234,567 / m³"       │                      │
  │                   │                    │◄─────────────────────────┤                      │
  │                   │                    │                          │                      │
  │                   │                    │ 7. Guarda conversación   │                      │
  │                   │                    ├─────────────────────────────────────────►       │
  │                   │                    │                          │                      │
  │                   │  {reply, sql_query,│                          │                      │
  │                   │   stages,          │                          │                      │
  │                   │   suggested_followups}                        │                      │
  │                   │◄───────────────────┤                          │                      │
  │ Muestra respuesta │                    │                          │                      │
  │◄──────────────────┤                    │                          │                      │
```

### 9.3 Asistente WhatsApp

```
Usuario (WhatsApp)       Twilio              Backend                    Gemini AI          MySQL
  │                       │                    │                          │                    │
  │ "dame el precio del   │                    │                          │                    │
  │  concreto 3000 psi"   │                    │                          │                    │
  ├──────────────────────►│                    │                          │                    │
  │                       │ POST /whatsapp_webhook                       │                    │
  │                       ├───────────────────►│                          │                    │
  │                       │                    │ Valida firma Twilio     │                    │
  │                       │                    │ Verifica usuario        │                    │
  │                       │                    ├────────────────────────────────────────────►  │
  │                       │                    │◄──────────────────────────────────────────┤   │
  │                       │                    │                          │                    │
  │                       │                    │ Prompt → Gemini          │                    │
  │                       │                    ├─────────────────────────►│                    │
  │                       │                    │◄─────────────────────────┤                    │
  │                       │                    │                          │                    │
  │                       │                    │ Valida SQL (read-only)   │                    │
  │                       │                    │ Ejecuta consulta         │                    │
  │                       │                    ├────────────────────────────────────────────►  │
  │                       │                    │◄──────────────────────────────────────────┤   │
  │                       │                    │                          │                    │
  │                       │                    │ Resumen → Gemini         │                    │
  │                       │                    ├─────────────────────────►│                    │
  │                       │                    │◄─────────────────────────┤                    │
  │                       │                    │                          │                    │
  │                       │                    │ Guarda conversación      │                    │
  │                       │                    ├────────────────────────────────────────────►  │
  │                       │                    │                          │                    │
  │                       │  Envía msg Twilio  │                          │                    │
  │                       │◄───────────────────┤                          │                    │
  │ "Concreto 3000 psi    │                    │                          │                    │
  │  Proyecto XYZ:        │                    │                          │                    │
  │  $850,000 / m³..."    │                    │                          │                    │
  │◄──────────────────────┤                    │                          │                    │
```

### 9.4 Flujo de Aprobación de APUs

```
CONTRAPARTE               ANALISTA                   SUBGERENTE              LEGAL
    │                        │                          │                      │
    │ Sube archivos PDF/Excel│                          │                      │
    ├───────────────────────►│                          │                      │
    │                        │ POST /analisis-apu/upload│                      │
    │                        │   → crear_solicitud()   │                      │
    │                        │   → realizar_analisis() │                      │
    │                        │                          │                      │
    │                        │ Estado: analizado        │                      │
    │                        │                          │                      │
    │                        │ Revisa análisis IA       │                      │
    │                        │                          │                      │
    │      ┌─────────────────┼────────────────────┐     │                      │
    │      │                 │                    │     │                      │
    │      ▼                 ▼                    ▼     │                      │
    │  Si acepta        Si rechaza            Si duda   │                      │
    │      │                 │                    │     │                      │
    │      │ POST /preaprobar│ POST /rechazar     │     │                      │
    │      │                 │                    │     │                      │
    │      ▼                 ▼                    ▼     │                      │
    │  preaprobado      nuevas_cotizaciones    revisar  │                      │
    │      │                 │                          │                      │
    │      │                 │ Contraparte sube         │                      │
    │      │                 │ nuevas cotizaciones      │                      │
    │      │                 ├─────────────────────────►│                      │
    │      │                 │                          │                      │
    │      ▼                 ▼                          ▼                      │
    │  POST /aprobar-subgerente                     analizado (ciclo)         │
    │      │                 │                          │                      │
    │      ▼                 │                          │                      │
    │  aprobado_subgerente   │                          │                      │
    │      │                 │                          │                      │
    │      │ POST /firmar-legal                        │                      │
    │      ├───────────────────────────────────────────┤                      │
    │      │                 │                          │                      │
    │      ▼                 │                          ▼                      │
    │  aprobado_legal        │                     Se incorpora               │
    │                        │                     al banco de APUs            │
```

**Estados del flujo:**
```
pendiente_analisis → analizado → preaprobado → aprobado_subgerente → aprobado_legal
                                       ↘ rechazado → nuevas_cotizaciones → analizado
```

### 9.5 Consulta y Filtros

```
Usuario navega a /consulta-apus
         │
         ▼
Frontend carga opciones de filtro → GET /api/apus/filter-options
         │                              {proyectos, ciudades, tipos_insumo, ...}
         ▼
Frontend carga primera página → GET /api/apus?limit=50&offset=0
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      INTERFAZ DE CONSULTA                                   │
│                                                                             │
│  [Buscar... ___________________________]                                    │
│                                                                             │
│  PROYECTO ▲  │  CIUDAD ▼  │  TIPO INSUMO ▼  │  PRECIO UNIT.  │  ...       │
│  ───────────  │  ────────  │  ─────────────  │  ─────────────  │            │
│  Proyecto A   │  Bogotá    │  Materiales     │   $1,234,567    │            │
│  Proyecto B   │  Medellín  │  Mano de obra   │     $850,000    │            │
│  ...          │  ...       │  ...             │  ...            │            │
│                                                                             │
│  ← 1 2 3 ... 10 →                                  Mostrando 50 de 1,234  │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
El usuario puede:
  • Escribir en la barra de búsqueda global → GET /api/apus?search=texto
  • Hacer clic en encabezado para ordenar → GET /api/apus?sort_by=precio_unitario&sort_order=desc
  • Abrir menú de filtro por columna → GET /api/apus?ciudad=Bogotá
  • Navegar páginas → GET /api/apus?offset=50
```

---

## 10. Configuración y Despliegue

### Variables de Entorno (`.env`)

| Variable | Descripción | Requerido |
|----------|-------------|-----------|
| `AI_PROVIDER` | `gemini` u `ollama` | Sí |
| `GEMINI_API_KEY` | API key de Google Gemini | Si provider=gemini |
| `GEMINI_MODEL` | Modelo Gemini (default: `gemini-2.5-flash`) | No |
| `DB_HOST` | Host de MySQL | Sí |
| `DB_PORT` | Puerto (default: 5432) | No |
| `DB_NAME` | Nombre de la BD | Sí |
| `DB_USER` | Usuario de BD | Sí |
| `DB_PASSWORD` | Contraseña de BD | Sí |
| `DB_SSLMODE` | Modo SSL (`prefer`, `require`, `disable`) | No |
| `JWT_SECRET_KEY` | Clave secreta para JWT | **Sí en producción** (el servidor no arranca sin ella si `ENV=production`) |
| `ACCOUNT_SID` | SID de Twilio | Solo WhatsApp |
| `AUTH_TOKEN` | Token de Twilio | Solo WhatsApp |
| `FROM_WHATSAPP` | Número remitente Twilio | Solo WhatsApp |
| `CORS_ORIGINS` | Orígenes CORS (separados por coma) | No |

### Ejecución Local

```bash
# 1. Iniciar MySQL
docker compose up -d mysql

# 2. Iniciar backend
uvicorn main:app --reload --port 10000

# 3. Iniciar frontend (desarrollo)
cd frontend
npm install && npm start
```

### Despliegue con Docker Compose

```bash
docker compose up -d
# mysql:3307, api:10000, frontend:8080
```

### Despliegue en Producción (Heroku)

```bash
# Procfile ya configurado
git push heroku main
```

---

## 11. Guía para Desarrolladores

### Arquitectura de Capas

El proyecto sigue **Clean Architecture** con 4 capas:

```
┌──────────────────────────────────────────────────┐
│              PRESENTACIÓN (FastAPI)               │
│  Routers, auth, middleware, DTOs de entrada/salida│
├──────────────────────────────────────────────────┤
│              APLICACIÓN (Use Cases)               │
│  Orquestación de casos de uso del negocio         │
├──────────────────────────────────────────────────┤
│                 DOMINIO (Entities + Ports)        │
│  Reglas de negocio, interfaces abstractas         │
├──────────────────────────────────────────────────┤
│             INFRAESTRUCTURA (Implementaciones)    │
│  BD, IA, Jobs, parsers, validadores               │
└──────────────────────────────────────────────────┘
```

**Regla de dependencia:** Las capas externas dependen de las internas, nunca al revés. La capa de dominio no sabe nada de FastAPI, MySQL ni Gemini.

### Cómo Agregar una Nueva Columna a la Tabla `apus`

1. **Base de datos:** Agregar ALTER TABLE en `src/infrastructure/database/schema.py` (`SCHEMA_STATEMENTS`)
2. **Entidad:** Agregar campo en `src/domain/entities/apu.py` (clase `ApuRecord`)
3. **Infraestructura:** Actualizar INSERT en `src/infrastructure/database/repositories/apu_repository.py`
4. **Limpieza:** Actualizar `post_process_extracted_data()` en `src/infrastructure/ai/gemini_extractor.py`
5. **Frontend:** Agregar columna en `frontend/src/app/pages/consulta-apus/consulta-apus.ts` (array `columns`)
6. **Interfaz:** Actualizar `ApuRecord` en `frontend/src/app/services/apu.ts`
7. **Prompt:** Opcionalmente actualizar schema en `src/infrastructure/ai/gemini_prompts.py`

### Cómo Agregar un Nuevo Endpoint

1. Crear o modificar un router en `src/presentation/routers/`
2. Agregar caso de uso en `src/application/use_cases/` (si aplica)
3. Agregar lógica de infraestructura en `src/infrastructure/` (si aplica)
4. Registrar el router en `src/presentation/main.py` (vía `create_app()`)
5. Agregar método en `frontend/src/app/services/apu.ts`

### Pruebas

```bash
# Backend (35 tests)
pytest tests/ -v

# Frontend
cd frontend
npm test
```

### Estilo de Código

- **Python:** PEP 8, ruff (line-length=120), nombres descriptivos en español (dominio del proyecto)
- **TypeScript:** Angular style guide, interfaces para modelos, services para API
- **Imports Python:** Orden: builtins → third-party → módulos del proyecto
- **Errores:** Los endpoints capturan excepciones y retornan HTTP status codes apropiados. El frontend maneja errores en callbacks `error`.

---

*Documentación generada para desarrolladores — MAPUS v2.1.0*
