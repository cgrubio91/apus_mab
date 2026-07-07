"""Create initial admin user in the database.

Uso:
    python scripts/create_user.py <telefono> <nombre> [rol]

La contraseña se lee de la variable de entorno ADMIN_PASSWORD
(nunca se hardcodea en el repositorio).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.infrastructure.database.connection import execute_query
from src.presentation.auth import hash_password

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(1)

telefono = sys.argv[1]
nombre = sys.argv[2]
rol = sys.argv[3] if len(sys.argv) > 3 else "admin"
password = os.getenv("ADMIN_PASSWORD")

if not password or len(password) < 6:
    print("Error: define ADMIN_PASSWORD (mínimo 6 caracteres) en el entorno.")
    sys.exit(1)

pw_hash = hash_password(password)
execute_query(
    """INSERT INTO usuarios (telefono, nombre, rol, activo, password_hash)
       VALUES (%s, %s, %s, %s, %s)
       ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash), activo = true""",
    (telefono, nombre, rol, True, pw_hash),
    fetch=False,
)
print(f"Usuario creado: {telefono} / rol={rol}")
