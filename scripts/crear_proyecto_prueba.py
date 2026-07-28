"""Crea un PROYECTO DE PRUEBA con su presupuesto a partir de un Excel de Acta
(export de item_proyecto). Sirve para simular el flujo completo: asignar una
cotización de Análisis APU a este proyecto y ver cómo el ítem NP se carga en su
presupuesto al firmar legal.

Crea:
  - 1 fila en `proyectos`
  - filas en `item_proyecto` (capítulos nivel 1 + ítems nivel 2)

NO toca el banco `apus`. Si el proyecto de prueba ya existe (misma descripción),
lo borra y lo vuelve a crear (recarga limpia).

Uso:
    # Ver el plan (no toca nada):
    DB_HOST=localhost DB_PORT=3307 DB_USER=postgres DB_PASSWORD=postgres \
    DB_NAME=interventoria python scripts/crear_proyecto_prueba.py "<ruta_excel>"

    # Aplicar:
    ... python scripts/crear_proyecto_prueba.py "<ruta_excel>" --apply
"""

import os
import sys
from pathlib import Path

import mysql.connector
import openpyxl

DESC_PROYECTO = "VÍAS DEL RENACIMIENTO — SONSÓN (PRUEBA MAPUS)"
ID_FOLDER = "PRUEBA-VDR"

# Índices de columna (0-based) según el encabezado del Acta (fila 3).
C_ITEM, C_EGRAL, C_EPART, C_GAJUS, C_DESC, C_AI, C_AIU, C_UND, C_CANT, C_VUNIT, C_VALOR = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _leer_presupuesto(ruta: str) -> list:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    ws = wb.active
    filas = []
    orden = 0
    for r in ws.iter_rows(min_row=4, values_only=True):
        item = (str(r[C_ITEM]).strip() if r[C_ITEM] is not None else "")
        desc = (str(r[C_DESC]).strip() if len(r) > C_DESC and r[C_DESC] is not None else "")
        if not item and not desc:
            continue
        orden += 1
        if item.lower().startswith("capitulo") or item.lower().startswith("capítulo"):
            filas.append({"tipo": "capitulo", "nombre": item, "orden": orden,
                          "valor_presupuestado": _num(r[C_VALOR])})
        elif item and desc:  # un ítem real tiene código Y descripción (los totales/reajustes no)
            filas.append({
                "tipo": "item", "orden": orden,
                "codigo": item, "nombre": desc or item,
                "especif_gral": (str(r[C_EGRAL]).strip() if r[C_EGRAL] else None),
                "especif_part": (str(r[C_EPART]).strip() if r[C_EPART] else None),
                "grupo_ajuste": (str(r[C_GAJUS]).strip() if r[C_GAJUS] else None),
                "unidad": (str(r[C_UND]).strip() if r[C_UND] else None),
                "cantidad": _num(r[C_CANT]), "valor_unitario": _num(r[C_VUNIT]),
                "valor_presupuestado": _num(r[C_VALOR]),
                "ai": _num(r[C_AI]), "aiu": _num(r[C_AIU]),
            })
    wb.close()
    return filas


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
    print(f"→ {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['database']}{' (SSL)' if 'ssl_ca' in cfg else ''}")
    return mysql.connector.connect(**cfg)


def main(ruta: str, aplicar: bool) -> None:
    if not Path(ruta).exists():
        raise SystemExit(f"No existe el Excel: {ruta}")
    filas = _leer_presupuesto(ruta)
    caps = [f for f in filas if f["tipo"] == "capitulo"]
    items = [f for f in filas if f["tipo"] == "item"]
    total = sum(i["valor_presupuestado"] or 0 for i in items)
    print(f"\n== PLAN ==\nProyecto: {DESC_PROYECTO}")
    print(f"Capítulos: {len(caps)} · Ítems: {len(items)} · Presupuesto total: ${total:,.0f}")
    for i in items[:6]:
        print(f"   {i['codigo']:12} {i['unidad'] or '-':>5}  cant={i['cantidad']}  vr={i['valor_unitario']}  {i['nombre'][:40]}")
    print(f"   ... ({len(items)} ítems en total)")

    if not aplicar:
        print("\n(DRY-RUN) No se creó nada. Añade --apply para ejecutar.")
        return

    cnx = _conectar()
    cur = cnx.cursor(dictionary=True)

    # Recarga limpia: borra el proyecto de prueba previo (y sus ítems).
    cur.execute("SELECT id FROM proyectos WHERE descripcion = %s", (DESC_PROYECTO,))
    for row in cur.fetchall():
        cur.execute("DELETE FROM item_proyecto WHERE proyecto = %s", (row["id"],))
        cur.execute("DELETE FROM proyectos WHERE id = %s", (row["id"],))

    cur.execute("SELECT COALESCE(MAX(id_proy), 9000) + 1 AS n FROM proyectos")
    id_proy = cur.fetchone()["n"]
    cur.execute(
        "INSERT INTO proyectos (id_proy, descripcion, presupuesto_total, id_folder) VALUES (%s, %s, %s, %s)",
        (id_proy, DESC_PROYECTO, total, ID_FOLDER),
    )
    proyecto_id = cur.lastrowid

    cap_actual = None
    n_ins = 0
    for f in filas:
        if f["tipo"] == "capitulo":
            cur.execute(
                """INSERT INTO item_proyecto (proyecto, parent_id, nivel, codigo, nombre,
                       valor_presupuestado, orden, tipo_item, aprobado_interventoria, aprobado_costos)
                   VALUES (%s, NULL, 1, %s, %s, %s, %s, 'PREVISTO', 1, 1)""",
                (proyecto_id, f["nombre"][:100], f["nombre"], f["valor_presupuestado"] or 0, f["orden"]),
            )
            cap_actual = cur.lastrowid
        else:
            cur.execute(
                """INSERT INTO item_proyecto (proyecto, parent_id, nivel, codigo,
                       especif_gral_raw, especif_part_raw, grupo_ajuste_raw, nombre, unidad_medida,
                       cantidad_presupuestada, valor_unitario, valor_presupuestado, ai, aiu, orden,
                       tipo_item, aprobado_interventoria, aprobado_costos)
                   VALUES (%s, %s, 2, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'PREVISTO', 1, 1)""",
                (proyecto_id, cap_actual, f["codigo"], f["especif_gral"], f["especif_part"],
                 f["grupo_ajuste"], f["nombre"], f["unidad"], f["cantidad"], f["valor_unitario"],
                 f["valor_presupuestado"] or 0, f["ai"], f["aiu"], f["orden"]),
            )
            n_ins += 1

    cnx.commit()
    print(f"\n✔ Proyecto creado: id={proyecto_id}, id_proy={id_proy}")
    print(f"  Capítulos: {len(caps)} · Ítems: {n_ins} · Presupuesto: ${total:,.0f}")
    cur.close(); cnx.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ruta = args[0] if args else os.environ.get("ACTA_XLSX", "")
    main(ruta, aplicar="--apply" in sys.argv)
