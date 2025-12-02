# ===============================
# 📦 main.py — MAPUS BOT IA SQL + APU + CONTROL DE USUARIOS
# ===============================

from fastapi import FastAPI, Request
import mysql.connector
import requests
import json
import re
import os
import time
from twilio.rest import Client
from datetime import datetime
from dotenv import load_dotenv

# ===============================
# 🔑 CONFIGURACIÓN INICIAL
# ===============================
load_dotenv()
app = FastAPI()

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# DB (TiDB Cloud)
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 4000)),
}

# Configurar SSL para TiDB Cloud
ssl_ca_path = os.getenv("DB_SSL_CA", "isrgrootx1.pem")
if os.path.exists(ssl_ca_path):
    DB_CONFIG["ssl_ca"] = ssl_ca_path
    DB_CONFIG["ssl_verify_cert"] = True
    DB_CONFIG["ssl_verify_identity"] = True
else:
    # Intentar sin certificado específico
    DB_CONFIG["ssl_disabled"] = False


# Twilio
ACCOUNT_SID = os.getenv("ACCOUNT_SID")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
FROM_WHATSAPP = os.getenv("FROM_WHATSAPP")
client = Client(ACCOUNT_SID, AUTH_TOKEN)

# ===============================
# 🧠 FUNCIONES AUXILIARES
# ===============================
def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def gemini_generate(prompt: str) -> str:
    """Llama a la API de Gemini para generar texto."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=30)
        data = r.json()
        if "candidates" not in data:
            log(f"❌ Error Gemini: {json.dumps(data, indent=2)}")
            return "No se pudo procesar tu solicitud con la IA."
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        log(f"❌ Error conectando con Gemini: {e}")
        return "Error al conectar con la IA de Gemini."


def ejecutar_sql(query: str):
    """Ejecuta una consulta SQL y devuelve los resultados."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
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
    """Envía un mensaje de WhatsApp por Twilio."""
    try:
        client.messages.create(from_=FROM_WHATSAPP, to=to, body=text)
        log(f"✅ Mensaje enviado a {to}")
    except Exception as e:
        log(f"❌ Error enviando mensaje WhatsApp: {e}")


# ===============================
# 👥 CONTROL DE USUARIOS
# ===============================
def usuario_autorizado(telefono: str):
    """Verifica si el usuario está autorizado en la tabla 'usuarios'."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM usuarios WHERE telefono = %s AND activo = 1", (telefono,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        return user
    except Exception as e:
        log(f"❌ Error verificando usuario: {e}")
        return None


# ===============================
# 💬 ENDPOINT WHATSAPP WEBHOOK
# ===============================
@app.post("/whatsapp_webhook")
async def whatsapp_webhook(request: Request):
    """Procesa mensajes entrantes desde Twilio WhatsApp."""
    data = await request.form()
    from_number = data.get("From")
    message_body = data.get("Body", "").strip()

    log(f"📩 Mensaje recibido de {from_number}: {message_body}")

    # 🛡️ Verificación de usuario
    user = usuario_autorizado(from_number)
    if not user:
        send_whatsapp_message(from_number, "🚫 Acceso restringido.\nNo tienes permiso para usar este asistente.\nContacta con el administrador para solicitar acceso.")
        log(f"❌ Acceso denegado a {from_number}")
        return "UNAUTHORIZED"

    log(f"✅ Usuario autorizado: {user['nombre']} ({user['rol']})")

    if not message_body:
        send_whatsapp_message(from_number, f"👋 Hola {user['nombre']}! Envíame una pregunta sobre tus APUs o ítems, y te ayudaré con gusto.")
        return "OK"

    # ===============================
    # 🧠 PROMPT PARA SQL
    # ===============================
    prompt_sql = f"""
    Actúa como un asistente experto en bases de datos MySQL y en análisis de precios unitarios (APU) de obras civiles.
    Convierte la solicitud del usuario en una consulta SQL válida, basada en la tabla:

    Tabla: apus
    - fecha_aprobacion_apu, fecha_analisis_apu, ciudad, pais, entidad, contratista,
      nombre_proyecto, numero_contrato, item, items_descripcion, item_unidad,
      precio_unitario, precio_unitario_sin_aiu, codigo_insumo, tipo_insumo,
      insumo_descripcion, insumo_unidad, rendimiento_insumo, precio_unitario_apu,
      precio_parcial_apu, observacion, link_documento

    Reglas:
    - Solo genera consultas SELECT completas.
    - Si el usuario pide algo inexistente, responde: "Esa información no existe."
    - No uses formato Markdown ni ```sql```.

    Usuario: "{message_body}"
    """

    sql_query = gemini_generate(prompt_sql)
    sql_query = re.sub(r"```sql|```", "", sql_query).strip()
    log(f"🧠 SQL generado: {sql_query}")

    # ===============================
    # 🗃️ EJECUTAR CONSULTA SQL
    # ===============================
    if not sql_query.lower().startswith("select"):
        respuesta = "Solo se permiten consultas de lectura."
    else:
        resultados = ejecutar_sql(sql_query)
        log(f"📊 Resultados SQL: {resultados}")

        if not resultados or "error" in resultados[0]:
            respuesta = "No se encontraron resultados para tu consulta."
        else:
            prompt_resumen = f"""
            Eres un ingeniero experto en Análisis de Precios Unitarios (APU).
            Resume de manera clara, cálida y profesional (máximo 5 líneas) los resultados SQL,
            saludando al usuario por su nombre ({user['nombre']}) y cerrando con una despedida corta.
            Resultados: {json.dumps(resultados, ensure_ascii=False)}
            """
            respuesta = gemini_generate(prompt_resumen)

    # ===============================
    # 📤 ENVÍO DE RESPUESTA
    # ===============================
    if len(respuesta) > 1500:
        partes = [respuesta[i:i+1500] for i in range(0, len(respuesta), 1500)]
        for i, parte in enumerate(partes):
            send_whatsapp_message(from_number, parte)
            log(f"🗣️ Parte {i+1}/{len(partes)} enviada ({len(parte)} caracteres).")
            time.sleep(2)
    else:
        send_whatsapp_message(from_number, respuesta)
        log(f"🗣️ Respuesta enviada ({len(respuesta)} caracteres).")

    return "OK"


# ===============================
# 🏁 SERVIDOR LOCAL
# ===============================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    log(f"🚀 Iniciando servidor en puerto {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
z