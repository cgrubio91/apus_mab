import csv
import mysql.connector
from mysql.connector import Error
import chardet
# Ya no es necesario importar datetime

# ============ CONFIGURACIÓN ============
CSV_PATH = r"C:\Users\cgrub\Downloads\apus_csv\APUS_V1.csv"
BATCH_SIZE = 1000 # Define el tamaño del lote para la inserción masiva

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

# ============ FUNCIONES DE LIMPIEZA ============

def clean_numeric(value):
    """Limpia cadenas de números con formato monetario latino y las convierte a float."""
    if not value or value.strip() in ('–', '', 'NULL', 'null'): 
        return None
    
    clean_value = value.strip().replace('$', '').replace('€', '').strip()
    # Elimina el separador de miles (punto) y reemplaza la coma decimal por punto
    clean_value = clean_value.replace('.', '')
    clean_value = clean_value.replace(',', '.')

    try:
        return float(clean_value)
    except ValueError:
        return None 

# ===============================================
# NUEVA LÓGICA DE CARGA MASIVA
# ===============================================

DATA_TO_INSERT = []
errores = []
errores_db = []
header = []

print("Leyendo y limpiando datos del CSV...")

# 1. LEER Y LIMPIAR TODOS LOS DATOS EN MEMORIA
with open(CSV_PATH, "r", encoding=detectado["encoding"], errors="replace") as file:
    reader = csv.reader(file, delimiter=';') 
    header = next(reader)    # guardar encabezado para errores.csv

    for linea, row in enumerate(reader, start=2): 
        
        # A. Limpieza de Fechas (Índices 0, 1) - Asumiendo YYYY-MM-DD
        date_indices = [0, 1]
        for idx in date_indices:
            if not row[idx] or row[idx].strip() in ('–', '', 'NULL', 'null'):
                row[idx] = None
            # Si el valor está presente, se deja como está (debe ser YYYY-MM-DD)

        # B. Limpieza de Números (Índices: 11, 12, 17, 18, 19)
        numeric_indices = [11, 12, 17, 18, 19]
        valid_row = True
        try:
            for idx in numeric_indices:
                row[idx] = clean_numeric(row[idx])
        except Exception as e:
            # Si hay un error de formato, loguear y saltar
            # (Ej. un campo numérico tiene texto no esperado)
            print(f"❌ Error de limpieza numérica/conversión en fila {linea}: {e}")
            errores.append([linea] + row)
            valid_row = False
        
        if valid_row:
            # Añadir la fila limpia (como tupla) a la lista para inserción masiva
            DATA_TO_INSERT.append(tuple(row))


# 2. DEFINIR SENTENCIA SQL (La misma de antes)
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

# 3. EJECUTAR LA CARGA MASIVA EN LOTES
total = len(DATA_TO_INSERT)
exitos = 0

print(f"Total de filas limpiadas y listas para insertar: {total}")
print(f"Iniciando la carga en lotes de {BATCH_SIZE}...")

for i in range(0, total, BATCH_SIZE):
    batch = DATA_TO_INSERT[i:i + BATCH_SIZE]
    try:
        # Aquí es donde se usa la inserción por lotes
        cursor.executemany(sql, batch)
        exitos += len(batch)
        print(f"✅ Lote {i // BATCH_SIZE + 1} ({i + 2} a {i + len(batch) + 1}) insertado correctamente.")
    except Error as e:
        # En caso de error de lote, se registra y se continúa con el siguiente lote
        print(f"❌ Error al insertar el lote {i // BATCH_SIZE + 1} (Fila inicial en CSV: {i + 2}): {e}")
        errores_db.append(f"Lote que inicia en fila {i + 2}: {e}")
        continue 
        
conn.commit()
cursor.close()
conn.close()

print(f"\n✔ Total filas procesadas (limpias): {total}")
print(f"✔ Filas insertadas correctamente: {exitos}")
print(f"❌ Filas con error (formato): {len(errores)}")
print(f"❌ Errores de base de datos (por lote): {len(errores_db)}")


# Guardar archivo errores.csv (solo filas con error de formato)
if errores:
    with open("errores.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=';') # Usar delimitador ; para consistencia
        writer.writerow(["fila_original"] + header)
        writer.writerows(errores)
    print("📁 Archivo 'errores.csv' generado con las filas problemáticas (error de formato).")
else:
    print("🎉 No hubo errores de formato. Todos los registros fueron preparados.")