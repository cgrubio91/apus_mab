"""
📊 CSV to PostgreSQL Loader
Loads APU data from CSV file to PostgreSQL database with data cleaning and validation
"""

import csv
import os
from datetime import datetime
import chardet

from db_config import get_db_connection
from psycopg2 import Error

# ============ CONFIGURACIÓN ============
CSV_PATH = r"C:\Users\cgrub\Downloads\apus_csv\APUS_V1.csv"
BATCH_SIZE = 1000  # Tamaño del lote para inserción masiva


# ============ VERIFICAR ARCHIVO CSV ============
if not os.path.exists(CSV_PATH):
    print(f"❌ Error: No se encontró el archivo CSV en: {CSV_PATH}")
    exit()

# Detectar encoding del archivo
print(f"📂 Leyendo archivo: {CSV_PATH}")
with open(CSV_PATH, "rb") as f:
    detectado = chardet.detect(f.read())
print(f"🔎 Encoding detectado: {detectado['encoding']} (confianza: {detectado['confidence']:.2%})")


# ============ FUNCIONES DE LIMPIEZA ============

def clean_numeric(value):
    """Limpia cadenas de números con formato monetario latino y las convierte a float."""
    if not value or value.strip() in ('–', '', 'NULL', 'null', 'N/A', 'n/a'):
        return None
    
    clean_value = value.strip().replace('$', '').replace('€', '').replace(' ', '').strip()
    # Elimina el separador de miles (punto) y reemplaza la coma decimal por punto
    clean_value = clean_value.replace('.', '')
    clean_value = clean_value.replace(',', '.')

    try:
        return float(clean_value)
    except ValueError:
        return None


def clean_date(value):
    """Limpia y valida fechas. Espera formato YYYY-MM-DD."""
    if not value or value.strip() in ('–', '', 'NULL', 'null', 'N/A', 'n/a'):
        return None
    
    value = value.strip()
    
    # Si ya está en formato correcto, retornar
    try:
        datetime.strptime(value, '%Y-%m-%d')
        return value
    except ValueError:
        pass
    
    # Intentar otros formatos comunes
    formats = ['%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y', '%m-%d-%Y']
    for fmt in formats:
        try:
            date_obj = datetime.strptime(value, fmt)
            return date_obj.strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    return None


def clean_text(value):
    """Limpia campos de texto."""
    if not value or value.strip() in ('–', '', 'NULL', 'null', 'N/A', 'n/a'):
        return None
    return value.strip()


# ============ LEER Y LIMPIAR DATOS DEL CSV ============
DATA_TO_INSERT = []
errores = []
errores_db = []
header = []

print("\n📖 Leyendo y limpiando datos del CSV...")

with open(CSV_PATH, "r", encoding=detectado["encoding"], errors="replace") as file:
    reader = csv.reader(file, delimiter=';')
    header = next(reader)  # Guardar encabezado
    
    print(f"📋 Columnas encontradas en el CSV: {len(header)}")
    print(f"   {', '.join(header[:5])}... (mostrando primeras 5)")
    
    for linea, row in enumerate(reader, start=2):
        try:
            # Asegurarse de que la fila tenga el número correcto de columnas
            if len(row) < 22:
                print(f"⚠️  Fila {linea}: Tiene {len(row)} columnas, se esperaban 22. Saltando...")
                errores.append([linea] + row + ['ERROR: Columnas insuficientes'])
                continue
            
            # Crear una copia de la fila para limpiar
            cleaned_row = row.copy()
            
            # A. Limpieza de Fechas (Índices 0, 1)
            cleaned_row[0] = clean_date(row[0])  # fecha_aprobacion_apu
            cleaned_row[1] = clean_date(row[1])  # fecha_analisis_apu
            
            # B. Limpieza de Textos (Índices 2-10, 13-16, 20-21)
            text_indices = [2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16, 20, 21]
            for idx in text_indices:
                if idx < len(cleaned_row):
                    cleaned_row[idx] = clean_text(row[idx])
            
            # C. Limpieza de Números (Índices: 11, 12, 17, 18, 19)
            numeric_indices = [11, 12, 17, 18, 19]
            for idx in numeric_indices:
                if idx < len(cleaned_row):
                    cleaned_row[idx] = clean_numeric(row[idx])
            
            # Añadir la fila limpia como tupla
            DATA_TO_INSERT.append(tuple(cleaned_row))
            
            # Mostrar progreso cada 1000 filas
            if linea % 1000 == 0:
                print(f"   Procesadas {linea - 1} filas...")
                
        except Exception as e:
            print(f"❌ Error en fila {linea}: {e}")
            errores.append([linea] + row + [f'ERROR: {str(e)}'])

print(f"\n✅ Total de filas limpiadas y listas: {len(DATA_TO_INSERT)}")
print(f"❌ Filas con errores de formato: {len(errores)}")


# ============ INSERCIÓN MASIVA EN LOTES ============
print("\n🔌 Conectando a la base de datos...")

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    print("✅ Conexión exitosa")
except Exception as e:
    print(f"❌ Error al conectar: {e}")
    exit()

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

total = len(DATA_TO_INSERT)
exitos = 0
lotes_procesados = 0

if total > 0:
    print(f"\n🚀 Iniciando carga masiva en lotes de {BATCH_SIZE}...")
    print(f"   Total de lotes a procesar: {(total + BATCH_SIZE - 1) // BATCH_SIZE}")
    
    for i in range(0, total, BATCH_SIZE):
        batch = DATA_TO_INSERT[i:i + BATCH_SIZE]
        lotes_procesados += 1
        
        try:
            cursor.executemany(sql, batch)
            conn.commit()  # Commit después de cada lote exitoso
            exitos += len(batch)
            print(f"✅ Lote {lotes_procesados} ({len(batch)} registros) - Fila CSV inicial: {i + 2}")
            
        except Error as e:
            conn.rollback()  # Rollback en caso de error
            error_msg = f"Lote {lotes_procesados} (fila inicial CSV: {i + 2}): {str(e)}"
            print(f"❌ Error en {error_msg}")
            errores_db.append(error_msg)
            
            # Intentar insertar fila por fila en caso de error de lote
            print(f"   🔄 Intentando inserción fila por fila para este lote...")
            for j, row in enumerate(batch):
                try:
                    cursor.execute(sql, row)
                    conn.commit()
                    exitos += 1
                except Error as row_error:
                    conn.rollback()
                    fila_csv = i + j + 2
                    print(f"   ❌ Error en fila CSV {fila_csv}: {row_error}")
                    errores_db.append(f"Fila CSV {fila_csv}: {str(row_error)}")
else:
    print("\n⚠️  No hay datos para insertar.")

# ============ CERRAR CONEXIÓN ============
cursor.close()
conn.close()
print("\n🔒 Conexión cerrada.")

# ============ RESUMEN FINAL ============
print("\n" + "="*60)
print("📊 RESUMEN DE LA CARGA")
print("="*60)
print(f"✅ Total filas procesadas (limpias): {total}")
print(f"✅ Filas insertadas correctamente: {exitos}")
print(f"❌ Filas con error de formato: {len(errores)}")
print(f"❌ Errores de base de datos: {len(errores_db)}")
print(f"📦 Lotes procesados: {lotes_procesados}")

# Calcular tasa de éxito
if total > 0:
    tasa_exito = (exitos / total) * 100
    print(f"📈 Tasa de éxito: {tasa_exito:.2f}%")

# ============ GUARDAR ARCHIVOS DE ERROR ============
if errores:
    error_file = "errores_formato.csv"
    with open(error_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(["fila_original"] + header + ["error"])
        writer.writerows(errores)
    print(f"\n📁 Archivo '{error_file}' generado con {len(errores)} filas con errores de formato.")

if errores_db:
    error_db_file = "errores_database.txt"
    with open(error_db_file, "w", encoding="utf-8") as f:
        f.write("ERRORES DE BASE DE DATOS\n")
        f.write("="*60 + "\n\n")
        for error in errores_db:
            f.write(f"{error}\n")
    print(f"📁 Archivo '{error_db_file}' generado con {len(errores_db)} errores de base de datos.")

if not errores and not errores_db:
    print("\n🎉 ¡Carga completada sin errores!")

print("\n✨ Proceso finalizado.")
