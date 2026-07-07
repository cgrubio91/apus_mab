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


def _get_secret() -> str:
    # En producción settings.py ya falló al arranque si no hay clave;
    # el fallback solo aplica en desarrollo local.
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


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticación requerida")
    token = credentials.credentials
    payload = verify_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    rows = execute_query("SELECT id, telefono, nombre, rol, activo FROM usuarios WHERE id = %s", (user_id,))
    if not rows or not rows[0].get("activo"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo")
    return rows[0]


async def get_current_user_flexible(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token: Optional[str] = Query(default=None, include_in_schema=False),
):
    """Como get_current_user, pero acepta también el token por query param.

    Necesario para EventSource (SSE), que no permite enviar headers.
    """
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
