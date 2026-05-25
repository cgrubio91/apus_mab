# ==========================================================
# 📦 main.py — MAPUS CORE ENGINE & API (WHATSAPP + ANGULAR REST)
# ==========================================================

from fastapi import FastAPI, Request, UploadFile, File, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor

import requests
import json
import re
import os
import time
from datetime import datetime, date

# Import centralized database configuration
from db_config import get_db_connection, execute_query

# Import APU Extractor package services
from apu_extractor import (
    extract_text_from_excel,
    extract_text_from_pdf,
    extract_apus_from_text,
    extract_apus_from_pdf_multimodal,
    post_process_extracted_data,
    generate_copy_paste_table,
    insert_apus_batch,
    get_unique_projects,
    get_apus,
    delete_project_apus
)

try:
    from twilio.rest import Client
except Exception as e:
    print(f"⚠️ Twilio import failed: {e}")
    Client = None

# ==========================================================
# 🔑 INITIAL CONFIGURATION & CORS SETUP
# ==========================================================
app = FastAPI(
    title="MAPUS API",
    description="Procesador de APUs e Integración con Chatbots & Angular Frontend",
    version="2.0.0"
)

# Enable CORS for Angular frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your Angular host in production, e.g. ["http://localhost:4200"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gemini Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Twilio Config
if Client:
    ACCOUNT_SID = os.getenv("ACCOUNT_SID")
    AUTH_TOKEN = os.getenv("AUTH_TOKEN")
    FROM_WHATSAPP = os.getenv("FROM_WHATSAPP")
    client = Client(ACCOUNT_SID, AUTH_TOKEN)
else:
    ACCOUNT_SID = AUTH_TOKEN = FROM_WHATSAPP = None
    client = None

# ==========================================================
# 🧠 HELPER FUNCTIONS
# ==========================================================
def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def gemini_generate(prompt: str) -> str:
    """Calls the Gemini API to generate text."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=45)
        data = r.json()
        if "candidates" not in data:
            log(f"❌ Gemini Error: {json.dumps(data, indent=2)}")
            return "No se pudo procesar tu solicitud con la IA."
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        log(f"❌ Error connecting with Gemini: {e}")
        return "Error al conectar con la IA de Gemini."

def ejecutar_sql(query: str):
    """Executes a SQL query against PostgreSQL database and returns results."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        return rows
    except Exception as e:
        log(f"❌ SQL Error: {e}")
        return [{"error": str(e)}]
    finally:
        if conn:
            conn.close()

def send_whatsapp_message(to, text):
    """Sends a WhatsApp message via Twilio."""
    try:
        client.messages.create(from_=FROM_WHATSAPP, to=to, body=text)
        log(f"✅ Message sent to {to}")
    except Exception as e:
        log(f"❌ Error sending WhatsApp message: {e}")

# ==========================================================
# 👥 USER CONTROL & CONVERSATIONAL MEMORY
# ==========================================================
def usuario_autorizado(telefono: str):
    """Checks if the user is authorized in the 'usuarios' table."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM usuarios WHERE telefono = %s AND activo = true", (telefono,))
        user = cursor.fetchone()
        cursor.close()
        return user
    except Exception as e:
        log(f"❌ Error checking user: {e}")
        return None
    finally:
        if conn:
            conn.close()

def guardar_conversacion(telefono: str, mensaje_usuario: str, sql_generado: str, respuesta_bot: str):
    """Saves a conversation turn into the history table."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO historial_conversaciones (telefono, mensaje_usuario, sql_generado, respuesta_bot)
            VALUES (%s, %s, %s, %s)
        """, (telefono, mensaje_usuario, sql_generado, respuesta_bot))
        conn.commit()
        cursor.close()
        log(f"💾 Conversation stored for {telefono}")
    except Exception as e:
        log(f"⚠️ Error storing conversation: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def obtener_historial(telefono: str, limite: int = 5):
    """Retrieves the last N conversation records for a specific number."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT mensaje_usuario, sql_generado, respuesta_bot, timestamp
            FROM historial_conversaciones
            WHERE telefono = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (telefono, limite))
        historial = cursor.fetchall()
        cursor.close()
        return list(reversed(historial))  # Chronological order
    except Exception as e:
        log(f"⚠️ Error retrieving history: {e}")
        return []
    finally:
        if conn:
            conn.close()

# ==========================================================
# 🛡️ AUTOMATED DB SETUP ON STARTUP
# ==========================================================
@app.on_event("startup")
def setup_history_table():
    """Initializes tables like conversational history if they do not exist."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Create history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial_conversaciones (
                id SERIAL PRIMARY KEY,
                telefono VARCHAR(50) NOT NULL,
                mensaje_usuario TEXT NOT NULL,
                sql_generado TEXT,
                respuesta_bot TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create index
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_telefono_timestamp 
            ON historial_conversaciones (telefono, timestamp DESC)
        """)
        conn.commit()
        cursor.close()
        log("⚙️ Database schema verified. Table 'historial_conversaciones' is active.")
    except Exception as e:
        log(f"⚠️ Startup DB setup warning: {e}")
    finally:
        if conn:
            conn.close()

# ==========================================================
# 🩺 HEALTH CHECKS
# ==========================================================
@app.get("/")
def home():
    return {
        "status": "online", 
        "message": "APUs Processor Core Engine and API active 🚀",
        "endpoints": {
            "extract_file": "POST /api/extract-file",
            "save_extracted": "POST /api/save-extracted",
            "projects": "GET /api/projects",
            "apus": "GET /api/apus",
            "chat_assistant": "POST /api/chat-assistant",
            "whatsapp_webhook": "POST /whatsapp_webhook"
        }
    }

@app.get("/health")
def health_check():
    """Validates connectivity to the PostgreSQL database."""
    status = {"status": "ok", "database": "connected"}
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
    except Exception as e:
        status["status"] = "error"
        status["database"] = str(e)
        log(f"❌ Health check failed: {e}")
    finally:
        if conn:
            conn.close()
    return status

# ==========================================================
# 📂 FILE PROCESSING API (PDF / EXCEL INGESTION)
# ==========================================================
@app.post("/api/extract-file")
async def extract_file(file: UploadFile = File(...)):
    """
    Accepts a PDF or Excel file, extracts APU lines using Gemini AI, 
    and returns structured JSON along with a TSV text formatted for Google Sheets.
    """
    filename = file.filename
    content = await file.read()
    ext = os.path.splitext(filename)[1].lower()
    
    log(f"📥 Received file upload: {filename} ({len(content)} bytes)")
    
    try:
        raw_insumos = []
        
        if ext == ".pdf":
            # Direct base64 multimodal path (highly accurate layout/table translation)
            import base64
            pdf_base64 = base64.b64encode(content).decode("utf-8")
            log("📄 PDF file detected. Dispatching Gemini multimodal parser...")
            raw_insumos = extract_apus_from_pdf_multimodal(pdf_base64, filename)
            
        elif ext in (".xlsx", ".xls"):
            # Excel tabular text rendering path
            temp_dir = os.path.join(os.getcwd(), "temp")
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, filename)
            
            log(f"📊 Excel file detected. Saving temp file to: {temp_path}")
            with open(temp_path, "wb") as f:
                f.write(content)
                
            try:
                excel_text = extract_text_from_excel(temp_path)
                log("📊 Excel sheet values extracted to text matrix. Processing with Gemini...")
                raw_insumos = extract_apus_from_text(excel_text, filename)
            finally:
                # Always remove temp files
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        else:
            raise HTTPException(
                status_code=400, 
                detail="Formato no soportado. Por favor suba archivos PDF (.pdf) o planillas de Excel (.xlsx, .xls)."
            )
            
        # Post-process raw response (clean dates, numbers, formats)
        cleaned_insumos = post_process_extracted_data(raw_insumos, filename)
        
        # Generate copy-paste text table with semicolon/tab decimals (Spanish Latin standard)
        copy_paste_table = generate_copy_paste_table(cleaned_insumos)
        
        log(f"✅ Extracted {len(cleaned_insumos)} insumo lines successfully from: {filename}")
        
        return {
            "success": True,
            "filename": filename,
            "count": len(cleaned_insumos),
            "copy_paste_table": copy_paste_table,
            "insumos": cleaned_insumos
        }
        
    except Exception as e:
        log(f"❌ Error processing upload file: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error durante el procesamiento del archivo: {str(e)}"
        )

@app.post("/api/save-extracted")
async def save_extracted(payload: list):
    """
    Saves parsed and verified APU records directly to the database.
    Allows user review on frontend prior to committing records.
    """
    log(f"💾 Saving {len(payload)} APU lines to database...")
    try:
        res = insert_apus_batch(payload)
        log(f"💾 DB insertion results: success={res['success']}, count={res['count']}")
        return res
    except Exception as e:
        log(f"❌ Error saving to database: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================
# 📊 DB QUERIES & CRUD ENDPOINTS
# ==========================================================
@app.get("/api/projects")
async def get_projects():
    """Returns list of all unique project names present in DB."""
    try:
        projects = get_unique_projects()
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/apus")
async def get_apus_endpoint(
    nombre_proyecto: str = Query(None),
    ciudad: str = Query(None),
    items_descripcion: str = Query(None),
    insumo_descripcion: str = Query(None),
    tipo_insumo: str = Query(None),
    limit: int = Query(50),
    offset: int = Query(0)
):
    """Retrieves paginated, filtered APU records from the DB."""
    filters = {
        "nombre_proyecto": nombre_proyecto,
        "ciudad": ciudad,
        "items_descripcion": items_descripcion,
        "insumo_descripcion": insumo_descripcion,
        "tipo_insumo": tipo_insumo
    }
    # Prune null filters
    filters = {k: v for k, v in filters.items() if v is not None}
    
    try:
        res = get_apus(filters, limit, offset)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/projects")
async def delete_project(nombre_proyecto: str = Query(...)):
    """Deletes all APU records for a given project name."""
    log(f"🗑️ Deleting all records for project: {nombre_proyecto}")
    try:
        res = delete_project_apus(nombre_proyecto)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================
# 💬 FRONTEND CHAT ASSISTANT ENDPOINT
# ==========================================================
@app.post("/api/chat-assistant")
async def chat_assistant(payload: dict):
    """
    Exposes conversational APU search and summaries to the Angular UI.
    Receives text messages and returns the reply, executing query, and raw results.
    """
    message = payload.get("message", "").strip()
    telefono = payload.get("telefono", "web-user").strip()
    nombre_usuario = payload.get("nombre", "Usuario Web").strip()
    
    if not message:
        return {"reply": "Escribe una pregunta sobre tus APUs y te responderé con gusto."}
        
    log(f"💬 Web assistant query from {telefono}: {message}")
    
    try:
        # 1. Fetch History Context
        historial = obtener_historial(telefono, limite=5)
        contexto_historial = ""
        
        if historial:
            contexto_historial = "\n\nCONTEXTO DE CONVERSACIONES PREVIAS:\n"
            for i, conv in enumerate(historial, 1):
                contexto_historial += f"Usuario: {conv['mensaje_usuario']}\n"
                if conv['sql_generado']:
                    contexto_historial += f"SQL generado: {conv['sql_generado'][:100]}...\n"
            contexto_historial += "\nUSA ESTE CONTEXTO para entender referencias como 'el anterior', 'ese mismo', 'compara con...', etc.\n"
            
        # 2. Build prompting for SQL conversion
        prompt_sql = f"""
        Actúa como un asistente experto en bases de datos PostgreSQL y en análisis de precios unitarios (APU) de obras civiles.
        Convierte la solicitud del usuario en una consulta SQL válida, considerando que el usuario NO conoce los nombres técnicos de las columnas.
        
        Tabla: apus
        Columnas disponibles:
        - fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad, contratista,
          nombre_proyecto, numero_contrato, item, items_descripcion, item_unidad,
          precio_unitario, precio_unitario_sin_aiu, codigo_insumo, tipo_insumo,
          insumo_descripcion, insumo_unidad, rendimiento_insumo, precio_unitario_apu,
          precio_parcial_apu, observacion, link_documento
          
        REGLAS CRÍTICAS PARA BÚSQUEDAS:
        1. **BÚSQUEDAS FLEXIBLES** - Siempre usa ILIKE (case-insensitive) con % para búsquedas parciales.
        2. **MAPEO DE LENGUAJE NATURAL A COLUMNAS** (obra/proyecto -> nombre_proyecto, insumo/material -> insumo_descripcion, precio -> precio_unitario, etc.).
        3. Limita resultados a 20 con LIMIT 20.
        4. Si pide conteo, usa COUNT(*). Si pide promedio, usa AVG().
        5. Nunca uses igualdad exacta '=' para textos. Usa siempre ILIKE.
        6. Genera SOLO la consulta SQL SELECT, sin formato Markdown ni ```sql```.
        
        {contexto_historial}
        
        Usuario pregunta: "{message}"
        
        Genera SOLO la consulta SQL.
        """
        
        sql_query = gemini_generate(prompt_sql)
        sql_query = re.sub(r"```sql|```", "", sql_query).strip()
        log(f"🧠 Assistant SQL generated: {sql_query}")
        
        results = []
        if not sql_query.lower().startswith("select"):
            reply = "Lo siento, por seguridad solo puedo realizar operaciones de lectura."
        else:
            results = ejecutar_sql(sql_query)
            
            if not results or "error" in results[0]:
                reply = "No encontré registros que coincidan en la base de datos."
            else:
                # Clean up query results for JSON serialization (converts datetimes/decimals)
                serializable_results = []
                for row in results:
                    new_row = {}
                    for k, v in row.items():
                        if isinstance(v, (datetime, date)):
                            new_row[k] = v.strftime("%Y-%m-%d")
                        elif hasattr(v, '__float__'):  # Decimal or floats
                            new_row[k] = float(v) if v is not None else None
                        else:
                            new_row[k] = v
                    serializable_results.append(new_row)
                results = serializable_results
                
                # 3. Request Summary summary
                prompt_resumen = f"""
                Eres un ingeniero experto en Análisis de Precios Unitarios (APU).
                Resume de manera clara, cálida y profesional los resultados de la base de datos.
                Saluda brevemente al usuario ({nombre_usuario}).
                Resultados SQL: {json.dumps(results[:15], ensure_ascii=False)}
                Pregunta del usuario: "{message}"
                """
                reply = gemini_generate(prompt_resumen)
                
        # 4. Save to history
        guardar_conversacion(telefono, message, sql_query if sql_query.lower().startswith("select") else "", reply)
        
        return {
            "reply": reply,
            "sql_query": sql_query if sql_query.lower().startswith("select") else None,
            "results": results
        }
        
    except Exception as e:
        log(f"❌ Error in assistant endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================
# 💬 WHATSAPP WEBHOOK (EXISTING BOT COMPATIBILITY)
# ==========================================================
@app.post("/whatsapp_webhook")
async def whatsapp_webhook(request: Request):
    """Processes incoming Twilio WhatsApp webhook requests with full compatibility."""
    data = await request.form()
    from_number = data.get("From")
    message_body = data.get("Body", "").strip()

    log(f"📩 WhatsApp message from {from_number}: {message_body}")

    # 🛡️ User Auth
    user = usuario_autorizado(from_number)
    if not user:
        send_whatsapp_message(
            from_number, 
            "🚫 Acceso restringido.\nNo tienes permiso para usar este asistente.\nContacta con el administrador para solicitar acceso."
        )
        log(f"❌ Access denied to {from_number}")
        return "UNAUTHORIZED"

    log(f"✅ Authorized User: {user['nombre']} ({user['rol']})")

    if not message_body:
        send_whatsapp_message(
            from_number, 
            f"👋 Hola {user['nombre']}! Envíame una pregunta sobre tus APUs o ítems, y te ayudaré con gusto."
        )
        return "OK"

    # 1. Fetch conversational history context
    historial = obtener_historial(from_number, limite=5)
    contexto_historial = ""
    
    if historial:
        contexto_historial = "\n\nCONTEXTO DE CONVERSACIONES PREVIAS:\n"
        for i, conv in enumerate(historial, 1):
            contexto_historial += f"Usuario: {conv['mensaje_usuario']}\n"
            if conv['sql_generado']:
                contexto_historial += f"SQL generado: {conv['sql_generado'][:100]}...\n"
        contexto_historial += "\nUSA ESTE CONTEXTO para entender referencias como 'el anterior', 'ese mismo', 'compara con...', etc.\n"

    # 2. Build prompting for SQL conversion
    prompt_sql = f"""
    Actúa como un asistente experto en bases de datos PostgreSQL y en análisis de precios unitarios (APU) de obras civiles.
    Convierte la solicitud del usuario en una consulta SQL válida, considerando que el usuario NO conoce los nombres técnicos de las columnas.

    Tabla: apus
    Columnas disponibles:
    - fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad, contratista,
      nombre_proyecto, numero_contrato, item, items_descripcion, item_unidad,
      precio_unitario, precio_unitario_sin_aiu, codigo_insumo, tipo_insumo,
      insumo_descripcion, insumo_unidad, rendimiento_insumo, precio_unitario_apu,
      precio_parcial_apu, observacion, link_documento

    REGLAS CRÍTICAS PARA BÚSQUEDAS:
    1. **BÚSQUEDAS FLEXIBLES** - Siempre usa ILIKE (case-insensitive) con % para búsquedas parciales.
    2. **MAPEO DE LENGUAJE NATURAL A COLUMNAS** (obra -> nombre_proyecto, insumo -> insumo_descripcion, precio -> precio_unitario, etc.).
    3. Limita resultados a 20 con LIMIT 20 (a menos que el usuario especifique otra cantidad).
    4. Usa DISTINCT cuando sea necesario para evitar duplicados.
    5. Nunca uses '=' para textos (usa siempre ILIKE).
    6. Genera SOLO la consulta SQL SELECT, sin formato Markdown ni ```sql```.

    {contexto_historial}
    
    Usuario pregunta: "{message_body}"
    
    Genera SOLO la consulta SQL, sin explicaciones.
    """

    sql_query = gemini_generate(prompt_sql)
    sql_query = re.sub(r"```sql|```", "", sql_query).strip()
    log(f"🧠 WhatsApp SQL generated: {sql_query}")

    # 3. Execute SQL Query
    if not sql_query.lower().startswith("select"):
        respuesta = "Solo se permiten consultas de lectura."
    else:
        resultados = ejecutar_sql(sql_query)
        log(f"📊 Query execution results: {resultados}")

        if not resultados or "error" in resultados[0]:
            respuesta = "No se encontraron resultados para tu consulta."
        else:
            prompt_resumen = f"""
            Eres un ingeniero experto en Análisis de Precios Unitarios (APU).
            Presenta los resultados SQL de manera clara, profesional y bien formateada para WhatsApp.
            
            INSTRUCCIONES DE FORMATO:
            1. Saluda brevemente al usuario por su nombre: {user['nombre']}
            2. Analiza el tipo de consulta y formatea la respuesta apropiadamente:
               - **LISTADOS**: Usa numeración (1., 2., 3., etc.) con los datos más relevantes
               - **COMPARACIONES**: Usa formato de tabla simple con alineación, separando columnas con | 
               - **TOTALES/AGREGACIONES**: Presenta el resultado de forma clara y destacada
               - **CONSULTA SIMPLE**: Responde en 1-2 párrafos concisos
            
            3. Formato de tabla para comparaciones (ejemplo):
            ```
            Item                    | Precio      | Ciudad
            ----------------------------------------
            Excavación manual       | $45,000     | Bogotá
            Relleno compactado      | $32,500     | Medellín
            ```
            
            4. Formato de listado (ejemplo):
            ```
            1. Excavación manual - $45,000 (Bogotá)
            2. Relleno compactado - $32,500 (Medellín)
            ```
            
            5. Incluye solo la información más relevante. Si hay más de 15 resultados, resume los primeros 10-15 más importantes.
            6. Al final, menciona el total de registros encontrados si son muchos.
            7. Usa emojis sutiles para mejorar la lectura: 📊 💰 🏗️ 📍 ✅
            8. NO uses formato Markdown (**, __, etc.), usa MAYÚSCULAS para títulos.
            9. Mantén las líneas cortas (máximo 60 caracteres) para que se vean bien en WhatsApp.
            
            Pregunta del usuario: "{message_body}"
            Resultados SQL: {json.dumps(resultados, ensure_ascii=False, default=str)}
            """
            respuesta = gemini_generate(prompt_resumen)

    # 4. Save to historical conversations
    guardar_conversacion(from_number, message_body, sql_query if sql_query.lower().startswith("select") else "", respuesta)

    # 5. Outbound chunking dispatch (limits messages to 1500 chars for WhatsApp delivery safety)
    if len(respuesta) > 1500:
        partes = [respuesta[i:i+1500] for i in range(0, len(respuesta), 1500)]
        for i, parte in enumerate(partes):
            send_whatsapp_message(from_number, parte)
            log(f"🗣️ WhatsApp chunk {i+1}/{len(partes)} dispatched ({len(parte)} chars).")
            time.sleep(2)
    else:
        send_whatsapp_message(from_number, respuesta)
        log(f"🗣️ WhatsApp reply dispatched ({len(respuesta)} chars).")

    return "OK"

# ==========================================================
# 🏁 RUN LOCAL SERVER
# ==========================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    log(f"🚀 Launching MAPUS FastAPI Server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
