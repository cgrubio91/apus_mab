import csv
import os
from db_config import get_db_connection

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "usuarios.csv")

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
            cursor.execute("SELECT id FROM users WHERE phone = %s", (telefono,))
            existing = cursor.fetchone()
            
            if existing:
                print(f"⚠️ Usuario {nombre} ({telefono}) ya existe. Actualizando...")
                cursor.execute("""
                    UPDATE users SET name = %s WHERE phone = %s
                """, (nombre, telefono))
            else:
                print(f"➕ Insertando usuario {nombre} ({telefono})...")
                cursor.execute("""
                    INSERT INTO users (name, cc, email, password, phone, position, proyecto)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (nombre, telefono, f"{telefono}@mapus.local", '', telefono, f"Rol: {rol}", "LOCAL"))
            
            cursor.execute("SELECT id FROM users WHERE phone = %s", (telefono,))
            user_row = cursor.fetchone()
            if user_row:
                cursor.execute("SELECT id FROM rol WHERE codigo = %s", (rol,))
                rol_row = cursor.fetchone()
                if rol_row:
                    cursor.execute("""
                        INSERT INTO usuario_rol (user_id, rol_id) VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE rol_id = %s
                    """, (user_row[0], rol_row[0], rol_row[0]))
        
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
