import logging
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

INTERVENTORIA_ROLE_MAP = {
    "super_admin": "admin",
    "director": "subgerente",
    "residente": "analista",
    "topografo": "contraparte",
    "inspector": "contraparte",
    "calidad": "contraparte",
    "bim": "contraparte",
}


def _resolve_mapus_role(interventoria_roles: list[str]) -> str:
    best_level = 0
    best_role = "contraparte"
    for r in interventoria_roles:
        clean = r.strip().lower()
        if clean in ROLES_HIERARCHY:
            mapped = clean
        else:
            mapped = INTERVENTORIA_ROLE_MAP.get(clean, "contraparte")
        level = ROLES_HIERARCHY.get(mapped, 0)
        if level > best_level:
            best_level = level
            best_role = mapped
    return best_role


def _get_secret() -> str:
    key = settings.JWT_SECRET_KEY
    if not key:
        log.warning("JWT_SECRET_KEY no configurada; usando clave de desarrollo insegura.")
    return key or "dev-only-insecure-key"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


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
            "activo": True,
        }

    return None


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
            "activo": True,
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
