"""
IDU Precios Unitarios Bulk Loader 2026

Descarga y procesa la matriz oficial de precios de referencia del IDU Bogotá
(Visor_BPR 2026) e inserta tanto los APUs como los Insumos en la base de datos
(`precio_referencia_externa`).

Uso:
    python idu_loader.py [--limit N] [--archivo RUTA_EXCEL]
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Asegurar que src está en sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.infrastructure.scraping.idu_source import IduSource
from src.infrastructure.database.repositories.referencia_externa_repository import (
    referencia_externa_repo,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("idu_loader")


def cargar_idu(ruta_excel: str = "", limite: int = 0) -> dict:
    source = IduSource()

    # 1. Asegurar descarga del archivo
    if not ruta_excel or not Path(ruta_excel).exists():
        log.info("Verificando/Descargando última versión de precios del IDU...")
        ruta_excel = source.descargar_excel("scratch/idu_2026.xlsx")
    else:
        log.info("Usando archivo provisto: %s", ruta_excel)

    # 2. Parsear APUs e Insumos
    log.info("Procesando hojas de APU e Insumos con openpyxl...")
    inicio_parse = time.time()
    apus, insumos = source.parsear_excel(ruta_excel)
    log.info(
        "Parseado en %.2f s: %d APUs completos y %d Insumos individuales",
        time.time() - inicio_parse,
        len(apus),
        len(insumos),
    )

    if limite > 0:
        apus = apus[:limite]
        insumos = insumos[:limite]
        log.info("Modo límite activado: procesando %d APUs y %d Insumos", len(apus), len(insumos))

    todos = apus + insumos
    total_registros = len(todos)
    if total_registros == 0:
        log.warning("No se encontraron registros para cargar.")
        return {"total": 0, "afectadas": 0}

    # 3. Inserción en lotes (batch upsert)
    batch_size = 500
    total_afectadas = 0
    inicio_carga = time.time()

    log.info("Iniciando carga a la BD en lotes de %d...", batch_size)
    for i in range(0, total_registros, batch_size):
        lote = todos[i : i + batch_size]
        try:
            res = referencia_externa_repo.upsert_muchas(lote)
            afectadas = res.get("afectadas", 0)
            total_afectadas += afectadas
            progreso = min(i + batch_size, total_registros)
            pct = (progreso / total_registros) * 100
            log.info("Lote %d-%d / %d (%.1f%%) insertado. Filas afectadas: %d", i + 1, progreso, total_registros, pct, afectadas)
        except Exception as e:
            log.exception("Error insertando lote %d: %s", i, e)

    tiempo_total = time.time() - inicio_carga
    log.info("=== CARGA IDU FINALIZADA ===")
    log.info("Total registros enviados: %d", total_registros)
    log.info("Total filas afectadas en BD: %d", total_afectadas)
    log.info("Tiempo de carga: %.2f segundos", tiempo_total)

    # Conteo total en BD
    total_en_bd = referencia_externa_repo.contar(fuente="IDU")
    log.info("Total actual de referencias IDU en BD: %d", total_en_bd)

    return {
        "total_enviados": total_registros,
        "apus": len(apus),
        "insumos": len(insumos),
        "afectadas": total_afectadas,
        "total_en_bd": total_en_bd,
    }


def main():
    parser = argparse.ArgumentParser(description="Carga masiva de APUs e Insumos IDU 2026")
    parser.add_argument("--limit", type=int, default=0, help="Límite de registros para prueba")
    parser.add_argument("--archivo", type=str, default="", help="Ruta manual al Excel de IDU")
    args = parser.parse_args()

    cargar_idu(ruta_excel=args.archivo, limite=args.limit)


if __name__ == "__main__":
    main()
