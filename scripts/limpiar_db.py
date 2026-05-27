from db_config import get_db_connection

def limpiar_tabla_apus():
    conn = get_db_connection()
    cur = conn.cursor()
    print("🧹 Limpiando tabla apus...")

    cur.execute("TRUNCATE TABLE apus RESTART IDENTITY CASCADE;")
    conn.commit()

    cur.close()
    conn.close()
    print("✅ Tabla apus vaciada correctamente.")

if __name__ == "__main__":
    limpiar_tabla_apus()
