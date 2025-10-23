# apus_mab# 🤖 MAPUS BOT — Asistente IA para APU en WhatsApp

MAPUS BOT es un asistente inteligente desarrollado por **MAB Ingeniería de Valor**, capaz de interpretar consultas en lenguaje natural sobre análisis de precios unitarios (APU) de obras civiles.  
Conecta inteligencia artificial, base de datos MySQL y mensajería por WhatsApp para brindar respuestas automáticas, rápidas y precisas.

## 🚀 Características principales

- **Interacción por WhatsApp:** El usuario envía consultas en lenguaje natural y recibe respuestas automáticas.  
- **Integración con Google Gemini:** Convierte texto libre en consultas SQL válidas y resume los resultados.  
- **Conexión con base de datos MySQL (Railway):** Extrae datos reales desde la tabla `apus`.  
- **Gestión de usuarios:** Solo números autorizados en la tabla `usuarios` pueden interactuar con el bot.  
- **API REST (FastAPI):** Implementado como microservicio compatible con despliegue en GCP (Cloud Run).  

## Arquitectura general

Usuario (WhatsApp)
↓
Twilio API
↓
MAPUS BOT (FastAPI)
↓
Google Gemini → genera SQL
↓
MySQL (Railway)
↓
Gemini → genera resumen
↓
Twilio → envía respuesta al usuario

## Estructura del proyecto
.
├── main.py # Lógica principal del bot (FastAPI + Gemini + Twilio + MySQL)
├── requirements.txt # Dependencias del entorno
├── runtime.txt # Versión de Python (para despliegue)
├── .env # Variables de entorno (no subir al repositorio)
├── .gitignore # Archivos excluidos de git
└── README.md # Documentación del proyecto

## ⚙️ Variables de entorno (.env)

```bash
# Gemini (Google Generative AI)
GEMINI_API_KEY=<clave_api_gemini>
GEMINI_MODEL=gemini-2.5-flash

# Twilio (WhatsApp)
ACCOUNT_SID=<tu_sid>
AUTH_TOKEN=<tu_token>
FROM_WHATSAPP=whatsapp:+14155238886

# Base de datos (Railway o Cloud SQL)
DB_HOST=<host>
DB_USER=<usuario>
DB_PASSWORD=<password>
DB_NAME=<nombre_db>
DB_PORT=<puerto>

Nota: El archivo .env debe estar incluido en .gitignore para evitar exponer credenciales sensibles.

Tabla usuarios — Control de acceso
Solo los usuarios activos pueden interactuar con el bot.
El sistema valida automáticamente el número remitente (From) contra esta tabla.

Estructura SQL
sql

CREATE TABLE usuarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  telefono VARCHAR(30) UNIQUE NOT NULL,
  nombre VARCHAR(100) NOT NULL,
  rol ENUM('admin', 'usuario', 'externo') DEFAULT 'usuario',
  activo BOOLEAN DEFAULT TRUE,
  fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

Ejemplo de flujo
Usuario (WhatsApp):

“Dame el precio unitario del concreto en Bogotá”

Gemini genera SQL:

SELECT item, precio_unitario, ciudad
FROM apus
WHERE ciudad = 'Bogotá' AND item LIKE '%concreto%';
Gemini resume resultados:

👷‍♂️ En Bogotá, los precios unitarios del concreto varían entre $420.000 y $460.000 por m³ según el proyecto.
¡Gracias por consultar con MAPUS BOT!

🧠 Estructura de la tabla apus
El modelo de IA se entrena para interpretar y generar consultas basadas en los siguientes campos:

Campo	Descripción
fecha_aprobacion_apu	Fecha de aprobación del APU
fecha_analisis_apu	Fecha del análisis
ciudad	Ciudad del proyecto
pais	País
entidad	Entidad contratante
contratista	Empresa ejecutora
nombre_proyecto	Nombre del proyecto
numero_contrato	Número del contrato
item	Código del ítem
items_descripcion	Descripción del ítem
item_unidad	Unidad de medida
precio_unitario	Valor unitario total
precio_unitario_sin_aiu	Valor unitario sin AIU
codigo_insumo	Código de insumo
tipo_insumo	Tipo de insumo (mano de obra, materiales, equipo, etc.)
insumo_descripcion	Descripción del insumo
insumo_unidad	Unidad del insumo
rendimiento_insumo	Rendimiento esperado
precio_unitario_apu	Valor unitario del insumo
precio_parcial_apu	Valor parcial del insumo
observacion	Comentarios adicionales
link_documento	Enlace al documento original

Dependencias
fastapi==0.115.2
uvicorn==0.30.6
mysql-connector-python==9.0.0
requests==2.32.3
twilio==9.2.3
python-dotenv==1.0.1
python-multipart==0.0.9

Instalación:
pip install -r requirements.txt

Ejecución local
python main.py

El servidor se levanta en:
http://localhost:10000

Endpoint del webhook:
/whatsapp_webhoo