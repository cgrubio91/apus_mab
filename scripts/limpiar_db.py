"""Vacía la tabla apus (MySQL). TRUNCATE reinicia el AUTO_INCREMENT."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from db_config import get_db_connection


def limpiar_tabla_apus():
    conn = get_db_connection()
    cur = conn.cursor()
    print("🧹 Limpiando tabla apus...")

    cur.execute("TRUNCATE TABLE apus;")
    conn.commit()

    cur.close()
    conn.close()
    print("✅ Tabla apus vaciada correctamente.")


if __name__ == "__main__":
    respuesta = input("Esto BORRA todos los registros de la tabla apus. ¿Continuar? (escribe SI): ")
    if respuesta.strip().upper() == "SI":
        limpiar_tabla_apus()
    else:
        print("Cancelado.")
