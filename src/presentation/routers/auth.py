import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.infrastructure.database.connection import execute_query
from src.presentation.auth import create_access_token, verify_password, hash_password

log = logging.getLogger("mapus.presentation.auth_router")
router = APIRouter()


class LoginRequest(BaseModel):
    telefono: str
    password: str


class RegisterRequest(BaseModel):
    telefono: str
    nombre: str
    password: str
    rol: str = "user"


@router.post("/auth/login", tags=["Auth"])
async def login(payload: LoginRequest) -> dict:
    rows = execute_query(
        "SELECT id, telefono, nombre, rol, activo, password_hash FROM usuarios WHERE telefono = %s",
        (payload.telefono,),
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    user = rows[0]
    if not user.get("activo"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")

    stored_hash = user.get("password_hash")
    if not stored_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    if not verify_password(payload.password, stored_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    token = create_access_token({
        "sub": str(user["id"]),
        "telefono": user["telefono"],
        "rol": user["rol"],
        "nombre": user["nombre"],
    })
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user["id"], "nombre": user["nombre"], "rol": user["rol"], "telefono": user["telefono"]},
    }


@router.post("/auth/register", tags=["Auth"])
async def register(payload: RegisterRequest) -> dict:
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")

    existing = execute_query("SELECT id FROM usuarios WHERE telefono = %s", (payload.telefono,))
    if existing:
        raise HTTPException(status_code=409, detail="El teléfono ya está registrado")

    password_hash = hash_password(payload.password)
    execute_query(
        "INSERT INTO usuarios (telefono, nombre, rol, password_hash) VALUES (%s, %s, %s, %s)",
        (payload.telefono, payload.nombre, payload.rol, password_hash),
        fetch=False,
    )
    log.info("Usuario registrado: %s (%s)", payload.telefono, payload.rol)
    return {"success": True, "mensaje": "Usuario registrado exitosamente"}
