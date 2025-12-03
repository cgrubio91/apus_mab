import csv
import os
from db_config import get_db_connection
from psycopg2 import Error

CSV_PATH = r"c:\Users\cgrub\OneDrive\Documents\apus_mab\apus_mab\usuarios.csv"

def load_users():
    if not os.path.exists(CSV_PATH):
        print(f"❌ Error: No se encontró el archivo CSV en: {CSV_PATH}")
        return

    print(f"📂 Leyendo archivo: {CSV_PATH}")
    
    users_to_insert = []
    
    # Read CSV with semi-colon delimiter
    with open(CSV_PATH, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file, delimiter=';')
        for row in reader:
            # Clean and prepare data
            telefono = row.get('telefono', '').strip()
            nombre = row.get('nombre', '').strip()
            rol = row.get('rol', '').strip()
            if not rol:
                rol = 'user'
            
            # Default active to True
            activo = True
            
            # Skip if phone is empty
            if not telefono:
                continue
                
            users_to_insert.append((nombre, telefono, rol, activo))

    print(f"✅ Se encontraron {len(users_to_insert)} usuarios para insertar.")

    if not users_to_insert:
        return

    print("\n🔌 Conectando a la base de datos...")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for nombre, telefono, rol, activo in users_to_insert:
            # Check if user exists
            cursor.execute("SELECT id FROM usuarios WHERE telefono = %s", (telefono,))
            existing = cursor.fetchone()
            
            if existing:
                print(f"⚠️ Usuario {nombre} ({telefono}) ya existe. Actualizando...")
                cursor.execute("""
                    UPDATE usuarios 
                    SET nombre = %s, rol = %s, activo = %s 
                    WHERE telefono = %s
                """, (nombre, rol, activo, telefono))
            else:
                print(f"➕ Insertando usuario {nombre} ({telefono})...")
                cursor.execute("""
                    INSERT INTO usuarios (nombre, telefono, rol, activo)
                    VALUES (%s, %s, %s, %s)
                """, (nombre, telefono, rol, activo))
        
        conn.commit()
        print("\n🎉 Usuarios procesados correctamente.")
        
    except Exception as e:
        print(f"❌ Error al conectar o insertar: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    load_users()
