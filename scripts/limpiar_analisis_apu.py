"""Borra los datos del flujo de Análisis APU (solicitudes, insumos cargados,
análisis, historial, aprendizaje y los ítems creados en proyectos por el flujo).

NO toca el banco de APUs (tabla `apus`).

Funciona en LOCAL y en PRODUCCIÓN (Aiven) según las variables de entorno,
igual que scripts/normalizar_ciudades_db.py.

Uso:
    # Ver qué se borraría (sin tocar nada):
    DB_HOST=localhost DB_PORT=3307 DB_USER=postgres DB_PASSWORD=postgres \
    DB_NAME=interventoria python scripts/limpiar_analisis_apu.py

    # Aplicar:
    ... python scripts/limpiar_analisis_apu.py --apply

    # Producción (Aiven) con SSL:
    DB_HOST=<host>.aivencloud.com DB_PORT=<port> DB_USER=<user> DB_PASSWORD=<pass> \
    DB_NAME=<db> DB_SSL_CA=ca.pem python scripts/limpiar_analisis_apu.py --apply
"""

import os
import sys
from pathlib import Path

import mysql.connector

# Hijo → padre para respetar dependencias.
PASOS = [
    ("aprendizaje_rechazos", "DELETE FROM aprendizaje_rechazos"),
    ("item_proyecto (creados por APU)", "DELETE FROM item_proyecto WHERE apu_solicitud_id IS NOT NULL"),
    ("analisis_apu", "DELETE FROM analisis_apu"),
    ("historial_aprobaciones", "DELETE FROM historial_aprobaciones"),
    ("solicitud_insumos", "DELETE FROM solicitud_insumos"),
    ("solicitudes_apu", "DELETE FROM solicitudes_apu"),
]

CONTEOS = [
    ("solicitudes_apu", "SELECT COUNT(*) FROM solicitudes_apu"),
    ("solicitud_insumos", "SELECT COUNT(*) FROM solicitud_insumos"),
    ("analisis_apu", "SELECT COUNT(*) FROM analisis_apu"),
    ("historial_aprobaciones", "SELECT COUNT(*) FROM historial_aprobaciones"),
    ("aprendizaje_rechazos", "SELECT COUNT(*) FROM aprendizaje_rechazos"),
    ("item_proyecto (creados por APU)", "SELECT COUNT(*) FROM item_proyecto WHERE apu_solicitud_id IS NOT NULL"),
]


def _conectar():
    cfg = {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "postgres"),
        "database": os.environ.get("DB_NAME", "interventoria"),
    }
    ssl_ca = os.environ.get("DB_SSL_CA")
    if ssl_ca and Path(ssl_ca).exists():
        cfg["ssl_ca"] = ssl_ca
        cfg["ssl_verify_cert"] = True
    print(f"→ Conectando a {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
          f"{' (SSL)' if 'ssl_ca' in cfg else ''}")
    return mysql.connector.connect(**cfg)


def main(aplicar: bool) -> None:
    cnx = _conectar()
    cur = cnx.cursor()

    print("\n== A BORRAR ==")
    for nombre, q in CONTEOS:
        cur.execute(q)
        print(f"  {nombre}: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM apus")
    print(f"\n== NO SE TOCA == banco apus: {cur.fetchone()[0]} filas")

    if not aplicar:
        print("\n(DRY-RUN) No se borró nada. Añade --apply para ejecutar.")
        cur.close(); cnx.close()
        return

    print("\nBorrando...")
    for nombre, q in PASOS:
        cur.execute(q)
        print(f"  {nombre}: {cur.rowcount} borrados")
    cnx.commit()

    print("\n== VERIFICACIÓN (deben ser 0) ==")
    for nombre, q in CONTEOS[:5]:
        cur.execute(q)
        print(f"  {nombre}: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM apus")
    print(f"\nBanco apus intacto: {cur.fetchone()[0]} filas")
    cur.close(); cnx.close()


if __name__ == "__main__":
    main(aplicar="--apply" in sys.argv)
