import csv
import chardet
import os

# ============ CONFIGURACIÓN ============
CSV_PATH = r"C:\Users\cgrub\Downloads\apus_csv\APUS_V1.csv"

# ============ VERIFICAR ARCHIVO ============
if not os.path.exists(CSV_PATH):
    print(f"❌ Error: No se encontró el archivo CSV en: {CSV_PATH}")
    exit()

print(f"📂 Analizando archivo: {CSV_PATH}")
print(f"📏 Tamaño del archivo: {os.path.getsize(CSV_PATH) / 1024 / 1024:.2f} MB")

# Detectar encoding
with open(CSV_PATH, "rb") as f:
    detectado = chardet.detect(f.read())

print(f"🔎 Encoding detectado: {detectado['encoding']} (confianza: {detectado['confidence']:.2%})")

# Leer primeras filas
print("\n" + "="*80)
print("📋 VISTA PREVIA DEL CSV")
print("="*80)

with open(CSV_PATH, "r", encoding=detectado["encoding"], errors="replace") as file:
    reader = csv.reader(file, delimiter=';')
    
    # Leer encabezado
    header = next(reader)
    print(f"\n✅ Columnas encontradas: {len(header)}")
    print("\n📌 ENCABEZADOS:")
    for idx, col in enumerate(header):
        print(f"   {idx:2d}. {col}")
    
    # Leer primeras 3 filas de datos
    print("\n📊 PRIMERAS 3 FILAS DE DATOS:")
    print("-"*80)
    
    for i, row in enumerate(reader):
        if i >= 3:
            break
        print(f"\n--- Fila {i+1} ---")
        for idx, (col_name, value) in enumerate(zip(header, row)):
            # Truncar valores muy largos
            display_value = value[:50] + "..." if len(value) > 50 else value
            print(f"   {idx:2d}. {col_name}: {display_value}")
    
    # Contar total de filas
    total_rows = i + 1
    for row in reader:
        total_rows += 1

print("\n" + "="*80)
print(f"📊 RESUMEN")
print("="*80)
print(f"Total de columnas: {len(header)}")
print(f"Total de filas de datos: {total_rows}")
print(f"Delimitador: ';' (punto y coma)")

# Verificar que coincida con la estructura de la tabla
expected_columns = 22
if len(header) == expected_columns:
    print(f"\n✅ El CSV tiene {expected_columns} columnas (coincide con la tabla 'apus')")
else:
    print(f"\n⚠️  ADVERTENCIA: El CSV tiene {len(header)} columnas, pero la tabla 'apus' espera {expected_columns}")
    print(f"   Esto puede causar errores durante la carga.")

print("\n✨ Análisis completado.")
print("\n💡 Si todo se ve bien, ejecuta 'load_apus_csv.py' para cargar los datos.")
