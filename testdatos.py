import csv
import chardet

ruta = r"C:\Users\cgrub\Downloads\apus_csv\APUS_V1.csv"

# Detectar encoding
with open(ruta, 'rb') as f:
    raw = f.read(200000)  # Leer un fragmento
    detect = chardet.detect(raw)
    encoding = detect['encoding']
    print("🔎 Encoding detectado:", encoding)

# Leer con el encoding detectado
with open(ruta, encoding=encoding, errors="replace") as f:
    reader = csv.reader(f)
    for i, row in enumerate(reader, start=1):
        pass

print("✔ Archivo leído correctamente")
