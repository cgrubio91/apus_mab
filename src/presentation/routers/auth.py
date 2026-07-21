import logging

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


class RegisterRequest(BaseModel):
    name: str
    email: str
    phone: str
    password: str


class LoginRequest(BaseModel):
    telefono: str
    password: str


class AdminUpdateUserRequest(BaseModel):
    rol: str | None = None
    activo: bool | None = None


class AdminCreateUserRequest(BaseModel):
    name: str
    email: str
    phone: str
    password: str
    rol: str = "contraparte"


@router.post("/auth/login", tags=["Auth"])
async def login(payload: LoginRequest) -> dict:
    from src.presentation.auth import _buscar_usuario_por_login

    user = _buscar_usuario_por_login(payload.telefono)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

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
        "user": {
            "id": user["id"],
            "nombre": user["nombre"],
            "rol": user["rol"],
            "telefono": user["telefono"],
            "email": user.get("email"),
        },
    }


@router.get("/auth/users", tags=["Auth"])
async def list_users(_admin: dict = Depends(require_role("admin"))) -> dict:
    rows = execute_query(
        """SELECT u.id, u.name, u.email, u.phone, u.position,
                  GROUP_CONCAT(DISTINCT r.codigo ORDER BY r.codigo SEPARATOR ',') AS roles_str
           FROM users u
           LEFT JOIN usuario_rol ur ON ur.user_id = u.id
           LEFT JOIN rol r ON r.id = ur.rol_id
           GROUP BY u.id
           ORDER BY u.id"""
    )
    return {"users": rows or []}


@router.patch("/auth/users/{user_id}", tags=["Auth"])
async def admin_update_user(
    user_id: int, payload: AdminUpdateUserRequest, admin: dict = Depends(require_role("admin"))
) -> dict:
    try:
        rows = execute_query("SELECT id FROM users WHERE id = %s", (user_id,))
    except Exception:
        rows = None

    if not rows:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if payload.rol is not None:
        if payload.rol not in ROLES_HIERARCHY:
            raise HTTPException(status_code=400, detail=f"Rol inválido. Roles válidos: {sorted(ROLES_HIERARCHY)}")
        rol_row = execute_query("SELECT id FROM rol WHERE codigo = %s", (payload.rol,))
        if not rol_row:
            raise HTTPException(status_code=400, detail=f"Rol '{payload.rol}' no encontrado en BD")
        execute_query(
            "INSERT INTO usuario_rol (user_id, rol_id) VALUES (%s, %s) ON DUPLICATE KEY UPDATE rol_id = %s",
            (user_id, rol_row[0]["id"], rol_row[0]["id"]),
            fetch=False,
        )

    if payload.activo is not None:
        if user_id == admin.get("id") and not payload.activo:
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")
        log.info("Solicitud de cambio de estado para user %s: activo=%s", user_id, payload.activo)

    log.info("Usuario %s actualizado por admin %s", user_id, admin.get("telefono"))
    return {"success": True, "mensaje": "Usuario actualizado"}


@router.post("/auth/register", tags=["Auth"])
async def register(payload: RegisterRequest) -> dict:
    if not payload.name or not payload.email or not payload.phone or not payload.password:
        raise HTTPException(status_code=400, detail="Todos los campos son requeridos")

    existing = execute_query(
        "SELECT id FROM users WHERE email = %s OR phone = %s",
        (payload.email, payload.phone),
    )
    if existing:
        raise HTTPException(status_code=400, detail="El email o teléfono ya está registrado")

    pwd_hash = hash_password(payload.password)
    execute_query(
        "INSERT INTO users (name, cc, email, password, phone, position, proyecto) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (payload.name, payload.phone, payload.email, pwd_hash, payload.phone, "Usuario MAPUS", "LOCAL"),
        fetch=False,
    )

    user_id = execute_query("SELECT LAST_INSERT_ID() AS id")[0]["id"]

    rol_row = execute_query("SELECT id FROM rol WHERE codigo = 'contraparte'")
    rol_id = rol_row[0]["id"] if rol_row else 12

    execute_query(
        "INSERT INTO usuario_rol (user_id, rol_id) VALUES (%s, %s)",
        (user_id, rol_id),
        fetch=False,
    )

    token = create_access_token({
        "sub": str(user_id),
        "telefono": payload.phone,
        "rol": "contraparte",
        "nombre": payload.name,
        "email": payload.email,
    })
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user_id, "nombre": payload.name, "rol": "contraparte", "telefono": payload.phone, "email": payload.email},
    }


@router.post("/auth/users", tags=["Auth"])
async def admin_create_user(payload: AdminCreateUserRequest, _admin: dict = Depends(require_role("admin"))) -> dict:
    if payload.rol not in ROLES_HIERARCHY:
        raise HTTPException(status_code=400, detail=f"Rol inválido. Roles válidos: {sorted(ROLES_HIERARCHY)}")

    existing = execute_query(
        "SELECT id FROM users WHERE email = %s OR phone = %s",
        (payload.email, payload.phone),
    )
    if existing:
        raise HTTPException(status_code=400, detail="El email o teléfono ya está registrado")

    pwd_hash = hash_password(payload.password)
    execute_query(
        "INSERT INTO users (name, cc, email, password, phone, position, proyecto) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (payload.name, payload.phone, payload.email, pwd_hash, payload.phone, f"Rol: {payload.rol}", "LOCAL"),
        fetch=False,
    )

    user_id = execute_query("SELECT LAST_INSERT_ID() AS id")[0]["id"]

    rol_row = execute_query("SELECT id FROM rol WHERE codigo = %s", (payload.rol,))
    if not rol_row:
        raise HTTPException(status_code=400, detail=f"Rol '{payload.rol}' no encontrado en BD")
    rol_id = rol_row[0]["id"]

    execute_query(
        "INSERT INTO usuario_rol (user_id, rol_id) VALUES (%s, %s)",
        (user_id, rol_id),
        fetch=False,
    )

    log.info("Admin creó usuario %d con rol '%s'", user_id, payload.rol)
    return {"success": True, "user_id": user_id, "rol": payload.rol}
