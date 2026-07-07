"""Amplía las columnas numéricas de la tabla apus a NUMERIC(30,10) (MySQL)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from db_config import get_db_connection

COLUMNAS = [
    "precio_unitario",
    "precio_unitario_sin_aiu",
    "rendimiento_insumo",
    "precio_unitario_apu",
    "precio_parcial_apu",
]


def ampliar_numericos():
    conn = get_db_connection()
    cur = conn.cursor()
    print("🔧 Ampliando columnas numéricas...")

    for col in COLUMNAS:
        cur.execute(f"ALTER TABLE apus MODIFY COLUMN {col} NUMERIC(30,10);")
    conn.commit()

    cur.close()
    conn.close()
    print("✅ Columnas numéricas ampliadas correctamente.")


if __name__ == "__main__":
    ampliar_numericos()
