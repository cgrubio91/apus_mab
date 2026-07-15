import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.infrastructure.database.connection import execute_query
from src.presentation.auth import (
    ROLES_HIERARCHY,
    create_access_token,
    hash_password,
    require_role,
    verify_password,
)

log = logging.getLogger("mapus.presentation.auth_router")
router = APIRouter()


class LoginRequest(BaseModel):
    telefono: str
    password: str


class RegisterRequest(BaseModel):
    telefono: str
    nombre: str
    email: str | None = None
    password: str


class AdminCreateUserRequest(BaseModel):
    telefono: str
    nombre: str
    email: str | None = None
    password: str
    rol: str = "user"


class AdminUpdateUserRequest(BaseModel):
    rol: str | None = None
    activo: bool | None = None


@router.post("/auth/login", tags=["Auth"])
async def login(payload: LoginRequest) -> dict:
    rows = execute_query(
        "SELECT id, telefono, nombre, email, rol, activo, password_hash FROM usuarios WHERE telefono = %s",
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
        "email": user.get("email"),
    })
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user["id"], "nombre": user["nombre"], "rol": user["rol"], "telefono": user["telefono"], "email": user.get("email")},
    }


def _crear_usuario(telefono: str, nombre: str, password: str, rol: str, email: str | None = None) -> None:
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")

    if email and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        raise HTTPException(status_code=400, detail="El correo electrónico no es válido")

    existing = execute_query("SELECT id FROM usuarios WHERE telefono = %s", (telefono,))
    if existing:
        raise HTTPException(status_code=409, detail="El teléfono ya está registrado")

    password_hash = hash_password(password)
    execute_query(
        "INSERT INTO usuarios (telefono, nombre, email, rol, password_hash) VALUES (%s, %s, %s, %s, %s)",
        (telefono, nombre, email, rol, password_hash),
        fetch=False,
    )
    log.info("Usuario registrado: %s (%s)", telefono, rol)


@router.post("/auth/register", tags=["Auth"])
async def register(payload: RegisterRequest) -> dict:
    # El registro público siempre crea usuarios con el rol mínimo; los roles
    # superiores solo se asignan desde los endpoints de administración.
    _crear_usuario(payload.telefono, payload.nombre, payload.password, rol="user", email=payload.email)
    return {"success": True, "mensaje": "Usuario registrado exitosamente"}


@router.get("/auth/users", tags=["Auth"])
async def list_users(_admin: dict = Depends(require_role("admin"))) -> dict:
    rows = execute_query(
        "SELECT id, telefono, nombre, email, rol, activo, fecha_registro FROM usuarios ORDER BY id"
    )
    return {"users": rows or []}


@router.post("/auth/users", tags=["Auth"])
async def admin_create_user(
    payload: AdminCreateUserRequest, _admin: dict = Depends(require_role("admin"))
) -> dict:
    if payload.rol not in ROLES_HIERARCHY:
        raise HTTPException(status_code=400, detail=f"Rol inválido. Roles válidos: {sorted(ROLES_HIERARCHY)}")
    _crear_usuario(payload.telefono, payload.nombre, payload.password, rol=payload.rol, email=payload.email)
    return {"success": True, "mensaje": "Usuario creado exitosamente"}


@router.patch("/auth/users/{user_id}", tags=["Auth"])
async def admin_update_user(
    user_id: int, payload: AdminUpdateUserRequest, admin: dict = Depends(require_role("admin"))
) -> dict:
    rows = execute_query("SELECT id FROM usuarios WHERE id = %s", (user_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if payload.rol is not None:
        if payload.rol not in ROLES_HIERARCHY:
            raise HTTPException(status_code=400, detail=f"Rol inválido. Roles válidos: {sorted(ROLES_HIERARCHY)}")
        execute_query("UPDATE usuarios SET rol = %s WHERE id = %s", (payload.rol, user_id), fetch=False)

    if payload.activo is not None:
        if user_id == admin.get("id") and not payload.activo:
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")
        execute_query("UPDATE usuarios SET activo = %s WHERE id = %s", (payload.activo, user_id), fetch=False)

    log.info("Usuario %s actualizado por admin %s", user_id, admin.get("telefono"))
    return {"success": True, "mensaje": "Usuario actualizado"}
