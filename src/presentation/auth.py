import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import PyJWTError

from src.config.settings import settings
from src.infrastructure.database.connection import execute_query

log = logging.getLogger("mapus.presentation.auth")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_EXPIRE_MINUTES

security = HTTPBearer(auto_error=False)

ROLES_HIERARCHY = {
    "admin": 100,
    "subgerente": 80,
    "legal": 60,
    "analista": 40,
    "contraparte": 20,
    "user": 10,
}

# Roles de interventoría (tabla rol) que traducen a un nivel MAPUS según su
# función real en el flujo de APUs: el residente técnico construye/revisa APU
# (como analista), el director aprueba (como subgerente) y el inspector apoya
# la parte comercial (como contraparte). Topógrafo/calidad/BIM no participan
# del flujo y siguen sin traducir.
EQUIVALENCIA_ROLES_INTERVENTORIA = {
    "director": ROLES_HIERARCHY["subgerente"],
    "residente": ROLES_HIERARCHY["analista"],
    "inspector": ROLES_HIERARCHY["contraparte"],
}

def _resolve_mapus_role(role_codes: list[str]) -> str:
    """Un usuario puede tener varios roles (su rol de interventoría + roles MAPUS
    adicionales, ver usuario_rol). Para efectos de autorización en MAPUS se toma
    el de mayor jerarquía entre los que sean roles MAPUS o tengan equivalencia
    de interventoría (ver EQUIVALENCIA_ROLES_INTERVENTORIA); el resto no traduce
    a un nivel y se ignora."""
    best_level = -1
    best_role = "user"
    for r in role_codes:
        clean = r.strip().lower()
        level = ROLES_HIERARCHY.get(clean, EQUIVALENCIA_ROLES_INTERVENTORIA.get(clean, -1))
        if level > best_level:
            best_level = level
            best_role = clean if clean in ROLES_HIERARCHY else _rol_mapus_de_intervertoria(clean)
    return best_role


def _rol_mapus_de_intervertoria(codigo: str) -> str:
    """Traduce un rol de interventoría a su rol MAPUS equivalente."""
    return {
        "director": "subgerente",
        "residente": "analista",
        "inspector": "contraparte",
    }.get(codigo, "user")


def _get_secret() -> str:
    key = settings.JWT_SECRET_KEY
    if not key:
        log.warning("JWT_SECRET_KEY no configurada; usando clave de desarrollo insegura.")
    return key or "dev-only-insecure-key"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def validar_password(password: str) -> None:
    """H6: política mínima de contraseñas (backend es la fuente autoritativa).

    Mínimo 8 caracteres, con al menos una letra y un dígito. Lanza ValueError
    con mensaje controlado (apto para detail 400) si no cumple.
    """
    if not password or len(password) < 8:
        raise ValueError("La contraseña debe tener mínimo 8 caracteres.")
    tiene_letra = any(c.isalpha() for c in password)
    tiene_digito = any(c.isdigit() for c in password)
    if not (tiene_letra and tiene_digito):
        raise ValueError("La contraseña debe incluir al menos una letra y un número.")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, _get_secret(), algorithm=ALGORITHM)


def _ahora_naive_utc() -> datetime:
    """MySQL DATETIME no guarda zona; se usa UTC naive en ambas direcciones."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def emitir_refresh_token(user_id: int) -> str:
    """Crea un refresh token opaco (7 días) y devuelve el valor en claro (única vez)."""
    raw = secrets.token_urlsafe(48)
    expira = _ahora_naive_utc() + timedelta(days=settings.REFRESH_EXPIRE_DAYS)
    execute_query(
        "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (user_id, _hash_token(raw), expira),
        fetch=False,
    )
    return raw


def rotar_refresh_token(raw: str) -> tuple[int, str] | None:
    """Valida un refresh token, lo revoca y emite uno nuevo (rotación).

    Devuelve (user_id, nuevo_token) o None si es inválido/expirado/revocado.
    """
    rows = execute_query(
        "SELECT id, user_id, expires_at, revoked FROM refresh_tokens WHERE token_hash = %s",
        (_hash_token(raw),),
    )
    if not rows:
        return None
    fila = rows[0]
    if fila.get("revoked") or not fila.get("expires_at") or fila["expires_at"] < _ahora_naive_utc():
        return None
    user_id = fila["user_id"]
    execute_query("UPDATE refresh_tokens SET revoked = 1 WHERE id = %s", (fila["id"],), fetch=False)
    return user_id, emitir_refresh_token(user_id)


def revocar_refresh_tokens(user_id: int) -> None:
    """Revoca todos los refresh tokens de un usuario (ej. tras cambiar la clave)."""
    try:
        execute_query(
            "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = %s AND revoked = 0",
            (user_id,),
            fetch=False,
        )
    except Exception:
        log.exception("Error revocando refresh tokens de user %s", user_id)


def emitir_reset_token(user_id: int) -> str:
    """Crea un token de recuperación de un solo uso y devuelve el valor en claro."""
    raw = secrets.token_urlsafe(32)
    expira = _ahora_naive_utc() + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
    execute_query(
        "INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (user_id, _hash_token(raw), expira),
        fetch=False,
    )
    return raw


def consumir_reset_token(raw: str) -> int | None:
    """Valida un token de recuperación, lo marca como usado y devuelve el user_id."""
    rows = execute_query(
        "SELECT id, user_id, expires_at, used_at FROM password_resets WHERE token_hash = %s",
        (_hash_token(raw or ""),),
    )
    if not rows:
        return None
    fila = rows[0]
    if fila.get("used_at") or not fila.get("expires_at") or fila["expires_at"] < _ahora_naive_utc():
        return None
    execute_query(
        "UPDATE password_resets SET used_at = %s WHERE id = %s",
        (_ahora_naive_utc(), fila["id"]),
        fetch=False,
    )
    return fila["user_id"]


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
    except PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")


def _buscar_usuario_por_id(user_id: int) -> dict | None:
    """Busca usuario en `users` con roles vía usuario_rol + rol."""
    try:
        rows = execute_query(
            """SELECT u.id, u.phone AS telefono, u.name AS nombre, u.email,
                      GROUP_CONCAT(DISTINCT r.codigo ORDER BY r.codigo SEPARATOR ',') AS roles_str
                FROM users u
                LEFT JOIN usuario_rol ur ON ur.user_id = u.id
                LEFT JOIN rol r ON r.id = ur.rol_id
                WHERE u.id = %s
                GROUP BY u.id""",
            (user_id,),
        )
    except Exception:
        rows = None

    if rows and rows[0].get("id"):
        u = rows[0]
        role_list = [x.strip() for x in (u.get("roles_str") or "").split(",") if x.strip()]
        return {
            "id": u["id"],
            "telefono": u.get("telefono") or "",
            "nombre": u["nombre"] or "",
            "email": u.get("email") or "",
            "rol": _resolve_mapus_role(role_list),
            "activo": _activo_usuario(u["id"]),
        }

    return None


def _activo_usuario(user_id: int) -> bool:
    """Lee la columna users.activo (migración idempotente en schema.py).

    Devuelve True si la columna aún no existe (BD sin migrar) para no
    bloquear logins durante el despliegue.
    """
    try:
        rows = execute_query("SELECT activo FROM users WHERE id = %s", (user_id,))
    except Exception:
        return True
    if not rows:
        return False
    val = rows[0].get("activo")
    return bool(val) if val is not None else True


def _buscar_usuario_por_login(identificador: str) -> dict | None:
    """Busca usuario por email o telefono en `users`."""
    try:
        rows = execute_query(
            """SELECT u.id, u.phone AS telefono, u.name AS nombre, u.email, u.password,
                      GROUP_CONCAT(DISTINCT r.codigo ORDER BY r.codigo SEPARATOR ',') AS roles_str
               FROM users u
               LEFT JOIN usuario_rol ur ON ur.user_id = u.id
               LEFT JOIN rol r ON r.id = ur.rol_id
               WHERE u.email = %s OR u.phone = %s
               GROUP BY u.id""",
            (identificador, identificador),
        )
    except Exception:
        rows = None

    if rows and rows[0].get("id"):
        u = rows[0]
        role_list = [x.strip() for x in (u.get("roles_str") or "").split(",") if x.strip()]
        return {
            "id": u["id"],
            "telefono": u.get("telefono") or "",
            "nombre": u["nombre"] or "",
            "email": u.get("email") or "",
            "password_hash": u.get("password"),
            "rol": _resolve_mapus_role(role_list),
            "activo": _activo_usuario(u["id"]),
        }

    return None


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticación requerida")
    token = credentials.credentials
    payload = verify_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    user = _buscar_usuario_por_id(user_id_int)
    if not user or not user.get("activo"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo")
    return user


async def get_current_user_flexible(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token: Optional[str] = Query(default=None, include_in_schema=False),
):
    if credentials is None and token:
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    return await get_current_user(credentials)


async def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_role(min_role: str):
    async def role_dependency(current_user: dict = Depends(get_current_user)):
        user_role = (current_user.get("rol") or "user").lower()
        min_level = ROLES_HIERARCHY.get(min_role, 0)
        user_level = ROLES_HIERARCHY.get(user_role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere rol '{min_role}' o superior. Tu rol: '{user_role}'",
            )
        return current_user
    return role_dependency
