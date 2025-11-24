# MAPUS BOT — Asistente IA para APU en WhatsApp

**MAPUS BOT** es un asistente inteligente desarrollado por **MAB Ingeniería de Valor**, capaz de interpretar consultas en lenguaje natural sobre análisis de precios unitarios (APU) de obras civiles.  
Integra inteligencia artificial, bases de datos MySQL y mensajería por WhatsApp para ofrecer respuestas automáticas, rápidas y precisas.

---

## 1. Características principales

- Interacción por WhatsApp: Permite realizar consultas en lenguaje natural y recibir respuestas automatizadas.
- Integración con Google Gemini: Convierte texto libre en consultas SQL y genera resúmenes comprensibles.
- Conexión con MySQL (Railway): Accede a datos reales desde la tabla `apus`.
- Gestión de usuarios: Solo los números registrados en la tabla `usuarios` pueden interactuar con el bot.
- API REST (FastAPI): Implementado como microservicio, compatible con despliegue en Google Cloud Run.

---

## 2. Arquitectura general
Usuario (WhatsApp)
↓
Twilio API
↓
MAPUS BOT (FastAPI)
↓
Google Gemini → Genera SQL
↓
MySQL (Railway)
↓
Gemini → Resume resultados
↓
Twilio → Envía respuesta al usuario

---

## 3. Estructura del proyecto

├── main.py              # Lógica principal (FastAPI + Gemini + Twilio + MySQL)
├── requirements.txt     # Dependencias del entorno
├── runtime.txt          # Versión de Python
├── .env                 # Variables de entorno (no subir al repositorio)
├── .gitignore           # Exclusiones de Git
└── README.md            # Documentación del proyecto

---

## 4. Base de datos

### Tabla `usuarios` — Control de acceso

El bot valida automáticamente el número remitente (`From`) contra esta tabla para determinar si puede interactuar.

#### Estructura SQL
CREATE TABLE usuarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  telefono VARCHAR(30) UNIQUE NOT NULL,
  nombre VARCHAR(100) NOT NULL,
  rol ENUM('admin', 'usuario', 'externo') DEFAULT 'usuario',
  activo BOOLEAN DEFAULT TRUE,
  fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

#### Datos de ejemplo

| id | teléfono               | nombre          | rol     | activo |
|----|------------------------|----------------|---------|--------|
| 1  | whatsapp:+573507698000 | Cristian Rubio  | admin   | 1      |
| 2  | whatsapp:+573222319000 | Yery Pedraza    | usuario | 1      |

---

### Tabla `apus` — Datos técnicos de obra

El modelo de IA genera consultas basadas en esta tabla.
Principales campos:

| Campo                   | Descripción                                              |
| ----------------------- | -------------------------------------------------------- |
| fecha_aprobacion_apu    | Fecha de aprobación del APU                              |
| fecha_analisis_apu      | Fecha del análisis                                       |
| ciudad                  | Ciudad del proyecto                                      |
| pais                    | País                                                     |
| entidad                 | Entidad contratante                                      |
| contratista             | Empresa ejecutora                                        |
| nombre_proyecto         | Nombre del proyecto                                      |
| numero_contrato         | Número del contrato                                      |
| item                    | Código del ítem                                          |
| items_descripcion       | Descripción del ítem                                     |
| item_unidad             | Unidad de medida                                         |
| precio_unitario         | Valor unitario total                                     |
| precio_unitario_sin_aiu | Valor sin AIU                                            |
| codigo_insumo           | Código de insumo                                         |
| tipo_insumo             | Tipo de insumo (mano de obra, materiales, equipos, etc.) |
| insumo_descripcion      | Descripción del insumo                                   |
| insumo_unidad           | Unidad del insumo                                        |
| rendimiento_insumo      | Rendimiento esperado                                     |
| precio_unitario_apu     | Valor unitario del insumo                                |
| precio_parcial_apu      | Valor parcial del insumo                                 |
| observacion             | Observaciones                                            |
| link_documento          | Enlace al documento fuente                               |

---

## 5. Ejemplo de flujo

Consulta (usuario por WhatsApp):
Dame el precio unitario del concreto en Bogotá

Consulta SQL generada por Gemini:
SELECT item, precio_unitario, ciudad
FROM apus
WHERE ciudad = 'Bogotá' AND item LIKE '%concreto%';

Respuesta del bot:
En Bogotá, los precios unitarios del concreto varían entre $420.000 y $460.000 por m³ según el proyecto.
Gracias por consultar con MAPUS BOT.

---

## 6. Instalación y ejecución

Dependencias
* fastapi==0.115.2
* uvicorn==0.30.6
* mysql-connector-python==9.0.0
* requests==2.32.3
* twilio==9.2.3
* python-dotenv==1.0.1
* python-multipart==0.0.9

Instalación
pip install -r requirements.txt

Ejecución local
python main.py

El servidor se levanta en:
http://localhost:10000

Endpoint del webhook:
/whatsapp_webhook

---

## 7. Variables de entorno (.env)

### Gemini (Google Generative AI)
GEMINI_API_KEY=<clave_api_gemini>
GEMINI_MODEL=gemini-2.5-flash

### Twilio (WhatsApp)
ACCOUNT_SID=<tu_sid>
AUTH_TOKEN=<tu_token>
FROM_WHATSAPP=whatsapp:+14155238886

### Base de datos (Railway o Cloud SQL)
DB_HOST=<host>
DB_USER=<usuario>
DB_PASSWORD=<password>
DB_NAME=<nombre_db>
DB_PORT=<puerto>

El archivo .env debe estar incluido en .gitignore para evitar exponer credenciales sensibles.

---

## 8. Créditos

Autor: Cristian Rubio
Empresa: MAB Ingeniería de Valor / MABTEC
Versión: 1.0.0
Lenguaje: Python 3.11
Framework: FastAPI
Base de datos: MySQL (Railway)
IA: Google Gemini
