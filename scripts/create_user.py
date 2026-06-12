"""Create initial admin user in the database."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.infrastructure.database.connection import execute_query
from src.presentation.auth import hash_password

telefono = "crubio@mab.com.co"
nombre = "Cristian Rubio"
password = "1064112177"
rol = "admin"

pw_hash = hash_password(password)
execute_query(
    """INSERT INTO usuarios (telefono, nombre, rol, activo, password_hash)
       VALUES (%s, %s, %s, %s, %s)
       ON CONFLICT (telefono)
       DO UPDATE SET password_hash = EXCLUDED.password_hash, activo = true""",
    (telefono, nombre, rol, True, pw_hash),
    fetch=False,
)
print(f"Usuario creado: {telefono} / rol={rol}")
