from db_config import get_db_connection

def ampliar_numericos():
    conn = get_db_connection()
    cur = conn.cursor()
    print("🔧 Ampliando columnas numéricas...")

    sql = """
    ALTER TABLE apus 
    ALTER COLUMN precio_unitario TYPE NUMERIC(30,10),
    ALTER COLUMN precio_unitario_sin_aiu TYPE NUMERIC(30,10),
    ALTER COLUMN rendimiento_insumo TYPE NUMERIC(30,10),
    ALTER COLUMN precio_unitario_apu TYPE NUMERIC(30,10),
    ALTER COLUMN precio_parcial_apu TYPE NUMERIC(30,10);
    """

    cur.execute(sql)
    conn.commit()

    cur.close()
    conn.close()
    print("✅ Columnas numéricas ampliadas correctamente.")

if __name__ == "__main__":
    ampliar_numericos()
