# ===============================
# 📦 main.py — MAPUS BOT IA SQL
# ===============================

from fastapi import FastAPI, Request
import mysql.connector
import requests
import json
import re
import os
from twilio.rest import Client
from datetime import datetime
from dotenv import load_dotenv

# ===============================
# 🔑 CONFIGURACIÓN INICIAL
# ===============================
load_dotenv()  # Carga variables desde .env

app = FastAPI()

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Base de datos (Railway)
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 58803)),  # 👈 puerto convertido a entero
}

# Twilio WhatsApp
ACCOUNT_SID = os.getenv("ACCOUNT_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_WHATSAPP = os.getenv("FROM_WHATSAPP")
client = Client(ACCOUNT_SID, AUTH_TOKEN)

# ===============================
# 🧠 FUNCIONES AUXILIARES
# ===============================
def log(msg):
    """Imprime logs con timestamp para depuración."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def gemini_generate(prompt: str) -> str:
    """Genera texto usando Gemini API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=30)
        data = r.json()
        if "candidates" not in data:
            log(f"❌ Error Gemini: {json.dumps(data, indent=2)}")
            return "No se pudo procesar tu solicitud con la IA."
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text
    except Exception as e:
        log(f"❌ Error conectando con Gemini: {e}")
        return "Error al conectar con la IA de Gemini."


def ejecutar_sql(query: str):
    """Ejecuta una consulta SQL y retorna resultados."""
    try:
        # 🔍 Log para verificar si las variables del entorno están cargadas
        log(f"🔍 DB Config usada: {DB_CONFIG}")

        if not all(DB_CONFIG.values()):
            log("⚠️ Variables de entorno incompletas. Revisa la configuración en Render.")
            return [{"error": "Configuración de base de datos incompleta."}]

        conn = mysql.connector.connect(**DB_CONFIG)
        log("✅ Conexión a la base de datos establecida correctamente.")
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception as e:
        log(f"❌ Error SQL: {e}")
        return [{"error": str(e)}]


def send_whatsapp_message(to, text):
    """Envía un mensaje de WhatsApp usando Twilio."""
    try:
        client.messages.create(from_=FROM_WHATSAPP, to=to, body=text)
        log(f"✅ Mensaje enviado a {to}")
    except Exception as e:
        log(f"❌ Error enviando mensaje WhatsApp: {e}")


# ===============================
# 💬 ENDPOINT WHATSAPP WEBHOOK
# ===============================
@app.post("/whatsapp_webhook")
async def whatsapp_webhook(request: Request):
    """Recibe mensajes entrantes de Twilio WhatsApp."""
    data = await request.form()
    from_number = data.get("From")
    message_body = data.get("Body", "").strip()

    log(f"📩 Mensaje recibido de {from_number}: {message_body}")

    if not message_body:
        send_whatsapp_message(from_number, "Por favor envíame una pregunta o solicitud válida.")
        return "OK"

    # ===============================
    # 🧠 Generar SQL con Gemini
    # ===============================
    prompt_sql = f"""
    Eres un asistente experto en SQL para MySQL.
    Convierte preguntas en consultas SQL válidas según esta estructura:

    Tabla: apus
    - fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad, contratista,
      nombre_proyecto, numero_contrato, item, items_descripcion, item_unidad,
      precio_unitario, precio_unitario_sin_aiu, codigo_insumo, tipo_insumo,
      insumo_descripcion, insumo_unidad, rendimiento_insumo, precio_unitario_apu,
      precio_parcial_apu, observacion, link_documento

    Solo genera consultas SELECT completas.
    Si el usuario pide algo inexistente, responde: "Esa información no existe".
    No incluyas formato Markdown ni bloques ```sql```.

    Usuario: "{message_body}"
    """

    sql_query = gemini_generate(prompt_sql)
    sql_query = re.sub(r"```sql|```", "", sql_query).strip()
    log(f"🧠 SQL generado: {sql_query}")

    # ===============================
    # 🗃️ Ejecutar consulta SQL
    # ===============================
    if not sql_query.lower().startswith("select"):
        respuesta = "Solo se permiten consultas de lectura."
    else:
        resultados = ejecutar_sql(sql_query)
        log(f"📊 Resultados SQL: {resultados}")

        # Si no hay resultados
        if not resultados or "error" in resultados[0]:
            respuesta = "No se encontraron resultados para tu consulta."
        else:
            prompt_resumen = f"Resume los siguientes resultados en lenguaje natural: {json.dumps(resultados, ensure_ascii=False)}"
            respuesta = gemini_generate(prompt_resumen)

    # ===============================
    # 📤 Enviar respuesta al usuario
    # ===============================
    send_whatsapp_message(from_number, respuesta)
    log(f"🗣️🌱 Respuesta enviada: {respuesta}")

    return "OK"


# ===============================
# 🏁 SERVIDOR LOCAL
# ===============================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    log(f"🚀 Iniciando servidor en puerto {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
