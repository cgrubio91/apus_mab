import csv
import mysql.connector
from mysql.connector import Error
import chardet

# ============ CONFIGURACIÓN ============
CSV_PATH = r"C:\Users\cgrub\Downloads\apus_csv\APUS_V1_UTF8.csv"

conn = mysql.connector.connect(
    host="gateway01.eu-central-1.prod.aws.tidbcloud.com",
    port=4000,
    user="3ZbVqta9Z98Eqp3.root",
    password="kyas1fDwE39EUqGZ",
    database="test",
    ssl_verify_cert=False,
    ssl_verify_identity=False
)

cursor = conn.cursor()

# Detectar encoding antes de leer
with open(CSV_PATH, "rb") as f:
    detectado = chardet.detect(f.read())
print(f"🔎 Encoding detectado: {detectado['encoding']}")

errores = []
total = 0
exitos = 0

with open(CCSV_PATH, "r", encoding=detectado["encoding"], errors="replace") as file:
    reader = csv.reader(file)
    header = next(reader)  # ignorar encabezado

    for linea, row in enumerate(reader, start=2):  # la fila 2 es la primera con datos
        total += 1
        try:
            sql = """
                INSERT INTO apus (
                    fecha_aprobacion_apu, fecha_analisis_apu,
                    ciudad, pais, entidad, contratista, nombre_proyecto,
                    numero_contrato, item, items_descripcion, item_unidad,
                    precio_unitario, precio_unitario_sin_aiu,
                    codigo_insumo, tipo_insumo, insumo_descripcion,
                    insumo_unidad, rendimiento_insumo,
                    precio_unitario_apu, precio_parcial_apu,
                    observacion, link_documento
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, row)
            exitos += 1

        except Error as e:
            print(f"❌ Error en fila {linea}: {e}")
            errores.append([linea] + row)
            continue

conn.commit()
cursor.close()
conn.close()

print(f"\n✔ Total filas procesadas: {total}")
print(f"✔ Filas insertadas correctamente: {exitos}")
print(f"❌ Filas con error: {len(errores)}")

# Guardar archivo errores.csv
if errores:
    with open("errores.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["fila_original"] + header)
        writer.writerows(errores)
    print("📁 Archivo 'errores.csv' generado con las filas problemáticas.")
else:
    print("🎉 No hubo errores. ¡Todos los registros fueron importados!")
