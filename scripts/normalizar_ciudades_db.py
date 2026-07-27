"""Normaliza los nombres de ciudad de la tabla `apus` en la base de datos.

Unifica variantes ("BOGOTA", "Bogotá D.C.", ...) al nombre canónico y mapea
IDU (Instituto de Desarrollo Urbano) → Bogotá. Usa la misma función que la
inserción de APUs (`src.infrastructure.geo.canonicalizar_ciudad`), así que el
resultado es consistente con las cargas nuevas.

Funciona en LOCAL y en PRODUCCIÓN (Aiven) según las variables de entorno.

Conexión (variables de entorno):
    DB_HOST, DB_PORT (3306), DB_USER, DB_PASSWORD, DB_NAME
    DB_SSL_CA   -> ruta al certificado CA (Aiven). Si se define, se usa SSL.

Uso:
    # Ver el plan sin cambiar nada (recomendado primero):
    DB_HOST=localhost DB_PORT=3307 DB_USER=postgres DB_PASSWORD=postgres \
    DB_NAME=interventoria python scripts/normalizar_ciudades_db.py

    # Aplicar los cambios:
    ... python scripts/normalizar_ciudades_db.py --apply

    # Producción (Aiven) — con SSL:
    DB_HOST=<host>.aivencloud.com DB_PORT=<port> DB_USER=<user> \
    DB_PASSWORD=<pass> DB_NAME=<db> DB_SSL_CA=ca.pem \
    python scripts/normalizar_ciudades_db.py --apply
"""

import os
import sys
from pathlib import Path

import mysql.connector

# Permite importar src.* al ejecutar desde la raíz del repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.infrastructure.geo import canonicalizar_ciudad  # noqa: E402


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
    cur = cnx.cursor(dictionary=True)

    # 1) IDU (entidad o ciudad) → Bogotá.
    cond_idu = ("(UPPER(TRIM(COALESCE(entidad,''))) = 'IDU' "
                "OR UPPER(TRIM(COALESCE(ciudad,''))) = 'IDU')")
    cur.execute(f"SELECT COUNT(*) AS n FROM apus WHERE {cond_idu} AND (ciudad IS NULL OR ciudad <> 'Bogotá')")
    n_idu = cur.fetchone()["n"]

    # 2) Unificación de variantes de nombre.
    cur.execute("SELECT ciudad, COUNT(*) AS n FROM apus "
                "WHERE ciudad IS NOT NULL AND TRIM(ciudad) <> '' GROUP BY ciudad")
    filas = cur.fetchall()

    cambios = []  # (valor_original, canonico, filas)
    for f in filas:
        original = f["ciudad"]
        canonico = canonicalizar_ciudad(original)
        if canonico and canonico != original:
            cambios.append((original, canonico, f["n"]))

    total_variantes = sum(c[2] for c in cambios)
    print(f"\n== PLAN DE NORMALIZACIÓN ==")
    print(f"IDU → Bogotá: {n_idu} fila(s)")
    print(f"Variantes a unificar: {len(cambios)} nombre(s) distintos, {total_variantes} fila(s)")
    for original, canonico, n in sorted(cambios, key=lambda c: -c[2])[:40]:
        print(f"   {n:>6}  '{original}'  →  '{canonico}'")
    if len(cambios) > 40:
        print(f"   ... y {len(cambios) - 40} más")

    if not aplicar:
        print("\n(DRY-RUN) No se aplicó ningún cambio. Añade --apply para ejecutar.")
        cur.close(); cnx.close()
        return

    print("\nAplicando cambios...")
    afectadas = 0
    if n_idu:
        cur.execute(f"UPDATE apus SET ciudad = 'Bogotá' WHERE {cond_idu} AND (ciudad IS NULL OR ciudad <> 'Bogotá')")
        afectadas += cur.rowcount
    for original, canonico, _ in cambios:
        cur.execute("UPDATE apus SET ciudad = %s WHERE ciudad = %s", (canonico, original))
        afectadas += cur.rowcount
    cnx.commit()
    print(f"✔ Listo. Filas actualizadas: {afectadas}")

    cur.execute("SELECT COUNT(DISTINCT ciudad) AS c FROM apus WHERE ciudad IS NOT NULL AND TRIM(ciudad) <> ''")
    print(f"Ciudades distintas ahora: {cur.fetchone()['c']}")
    cur.close(); cnx.close()


if __name__ == "__main__":
    main(aplicar="--apply" in sys.argv)
