"""
Backup periódico de MySQL (MAPUS).

Uso:
    python scripts/backup_mysql.py [--dest backups] [--retener 7]

Requiere `mysqldump` en el PATH y las variables DB_* en .env.
Programa la ejecución con cron (Linux) o Programador de tareas (Windows):

    # cron diario 2:00am, retiene 7 copias
    0 2 * * * cd /opt/apus_mab && python scripts/backup_mysql.py --retener 7
"""

import argparse
import gzip
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backup_mysql")


def hacer_backup(dest: Path, retener: int) -> Path:
    mysqldump = shutil.which("mysqldump")
    if not mysqldump:
        raise RuntimeError("mysqldump no está en el PATH; instálalo para usar este script.")
    if not all([settings.DB_HOST, settings.DB_NAME, settings.DB_USER, settings.DB_PASSWORD]):
        raise RuntimeError("Faltan DB_HOST/DB_NAME/DB_USER/DB_PASSWORD en el entorno o .env.")

    dest.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    salida = dest / f"mapus_{settings.DB_NAME}_{sello}.sql.gz"

    env = {**os.environ, "MYSQL_PWD": settings.DB_PASSWORD}
    cmd = [
        mysqldump, "-h", settings.DB_HOST, "-P", str(settings.DB_PORT),
        "-u", settings.DB_USER, "--single-transaction", "--routines",
        settings.DB_NAME,
    ]
    log.info("Respaldando %s...", settings.DB_NAME)
    proc = subprocess.run(cmd, capture_output=True, env=env, timeout=3600)
    if proc.returncode != 0:
        raise RuntimeError(f"mysqldump falló: {proc.stderr.decode(errors='replace')[:500]}")
    with gzip.open(salida, "wb") as fh:
        fh.write(proc.stdout)
    log.info("Backup OK: %s (%.1f MB)", salida, salida.stat().st_size / 1e6)

    copias = sorted(dest.glob("mapus_*.sql.gz"))
    for vieja in copias[:-retener] if len(copias) > retener else []:
        vieja.unlink()
        log.info("Copia antigua eliminada: %s", vieja.name)
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description="Backup de MySQL con mysqldump + gzip.")
    ap.add_argument("--dest", default="backups", help="Carpeta destino")
    ap.add_argument("--retener", type=int, default=7, help="Copias a retener")
    args = ap.parse_args()
    try:
        hacer_backup(Path(args.dest), args.retener)
    except Exception as e:
        log.error("Backup fallido: %s", e)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
