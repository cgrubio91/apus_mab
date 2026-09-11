import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.config.settings import settings
from src.infrastructure.database.connection import execute_query
from src.presentation.auth import (
    ROLES_HIERARCHY,
    consumir_reset_token,
    create_access_token,
    emitir_refresh_token,
    emitir_reset_token,
    hash_password,
    require_role,
    revocar_refresh_tokens,
    rotar_refresh_token,
    validar_password,
    verify_password,
)

log = logging.getLogger("mapus.presentation.auth_router")
router = APIRouter()


def _auditar(actor_id: int | None, accion: str, objetivo_tipo: str | None = None,
             objetivo_id: int | None = None, detalle: str | None = None) -> None:
    """Registra una acción administrativa (best-effort: nunca rompe el flujo)."""
    try:
        execute_query(
            """INSERT INTO auditoria_admin (actor_id, accion, objetivo_tipo, objetivo_id, detalle)
               VALUES (%s, %s, %s, %s, %s)""",
            (actor_id, accion, objetivo_tipo, objetivo_id, (detalle or "")[:500]),
            fetch=False,
        )
    except Exception:
        log.exception("Error registrando auditoría %s", accion)


def _tokens_para(user: dict) -> dict:
    """Par access + refresh para un usuario ya validado."""
    access = create_access_token({
        "sub": str(user["id"]),
        "telefono": user["telefono"],
        "rol": user["rol"],
        "nombre": user["nombre"],
        "email": user.get("email"),
    })
    try:
        refresh = emitir_refresh_token(user["id"])
    except Exception:
        log.exception("Error emitiendo refresh token para user %s", user["id"])
        refresh = None
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


class RegisterRequest(BaseModel):
    name: str | None = Field(None, examples=["Ana Pérez"])
    nombre: str | None = Field(None, examples=["Ana Pérez"])
    email: str | None = Field(None, examples=["ana@ejemplo.com"])
    phone: str | None = Field(None, examples=["3001234567"])
    telefono: str | None = Field(None, examples=["3001234567"])
    password: str = Field(..., description="Mín. 8 caracteres, con letra y número", examples=["Clave2026"])
    rol: str | None = Field(None, description="Se ignora en registro público: siempre 'user'")


class LoginRequest(BaseModel):
    telefono: str = Field(..., examples=["3001234567"])
    password: str = Field(..., examples=["Clave2026"])


class AdminUpdateUserRequest(BaseModel):
    rol: str | None = None
    activo: bool | None = None


class AdminCreateUserRequest(BaseModel):
    name: str
    email: str
    phone: str
    password: str
    rol: str = "contraparte"


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    identificador: str = Field(..., description="Email o teléfono de la cuenta")


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


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

    tokens = _tokens_para(user)
    return {
        **tokens,
        "user": {
            "id": user["id"],
            "nombre": user["nombre"],
            "rol": user["rol"],
            "telefono": user["telefono"],
            "email": user.get("email"),
        },
    }


@router.get("/auth/users", tags=["Auth"])
async def list_users(
    limite: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: dict = Depends(require_role("admin")),
) -> dict:
    base = """FROM users u
              LEFT JOIN usuario_rol ur ON ur.user_id = u.id
              LEFT JOIN rol r ON r.id = ur.rol_id"""
    try:
        rows = execute_query(
            f"""SELECT u.id, u.name, u.email, u.phone, u.position, u.activo,
                      GROUP_CONCAT(DISTINCT r.codigo ORDER BY r.codigo SEPARATOR ',') AS roles_str
               {base}
               GROUP BY u.id
               ORDER BY u.id LIMIT %s OFFSET %s""",
            (limite, offset),
        )
        total_rows = execute_query("SELECT COUNT(*) AS total FROM users")
    except Exception:
        # BD sin migrar (sin columna activo): fallback sin la columna.
        log.warning("list_users sin columna activo; usando fallback")
        rows = execute_query(
            f"""SELECT u.id, u.name, u.email, u.phone, u.position,
                      GROUP_CONCAT(DISTINCT r.codigo ORDER BY r.codigo SEPARATOR ',') AS roles_str
               {base}
               GROUP BY u.id
               ORDER BY u.id LIMIT %s OFFSET %s""",
            (limite, offset),
        )
        total_rows = execute_query("SELECT COUNT(*) AS total FROM users")
    for r in rows or []:
        if "activo" not in r:
            r["activo"] = True
        else:
            r["activo"] = bool(r["activo"]) if r["activo"] is not None else True
    total = total_rows[0]["total"] if total_rows else len(rows or [])
    return {"users": rows or [], "total": total, "limite": limite, "offset": offset}


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
        _auditar(admin.get("id"), "cambio_rol", "user", user_id, f"rol={payload.rol}")

    if payload.activo is not None:
        if user_id == admin.get("id") and not payload.activo:
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")
        try:
            execute_query(
                "UPDATE users SET activo = %s WHERE id = %s",
                (1 if payload.activo else 0, user_id),
                fetch=False,
            )
        except Exception:
            log.exception("Error actualizando estado de usuario %s", user_id)
            raise HTTPException(status_code=500, detail="No se pudo actualizar el estado del usuario.")
        log.info("Solicitud de cambio de estado para user %s: activo=%s", user_id, payload.activo)
        _auditar(admin.get("id"), "desactivar" if not payload.activo else "activar",
                 "user", user_id, None)

    log.info("Usuario %s actualizado por admin %s", user_id, admin.get("telefono"))
    return {"success": True, "mensaje": "Usuario actualizado"}


@router.post("/auth/register", tags=["Auth"])
async def register(payload: RegisterRequest) -> dict:
    name = (payload.name or payload.nombre or "").strip()
    phone = (payload.phone or payload.telefono or "").strip()
    email = (payload.email or f"{phone}@mapus.local" if phone else "").strip()

    if not name or not phone or not payload.password:
        raise HTTPException(status_code=400, detail="Nombre, teléfono y contraseña son requeridos")

    try:
        validar_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing = execute_query(
        "SELECT id FROM users WHERE (email = %s AND email <> '') OR phone = %s",
        (email, phone),
    )
    if existing:
        raise HTTPException(status_code=400, detail="El email o teléfono ya está registrado")

    pwd_hash = hash_password(payload.password)
    user_id = execute_query(
        "INSERT INTO users (name, cc, email, password, phone, position, proyecto) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (name, phone, email, pwd_hash, phone, "Usuario MAPUS", "LOCAL"),
        fetch=False,
        return_lastrowid=True,
    )

    # El registro público siempre asigna el rol base 'user' (id 13)
    rol_row = execute_query("SELECT id FROM rol WHERE codigo = 'user'")
    rol_id = rol_row[0]["id"] if rol_row else 13

    execute_query(
        "INSERT INTO usuario_rol (user_id, rol_id) VALUES (%s, %s)",
        (user_id, rol_id),
        fetch=False,
    )

    token = create_access_token({
        "sub": str(user_id),
        "telefono": phone,
        "rol": "user",
        "nombre": name,
        "email": email,
    })
    try:
        refresh = emitir_refresh_token(user_id)
    except Exception:
        log.exception("Error emitiendo refresh token en registro %s", user_id)
        refresh = None
    return {
        "success": True,
        "access_token": token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": {"id": user_id, "nombre": name, "rol": "user", "telefono": phone, "email": email},
    }


@router.post("/auth/users", tags=["Auth"])
async def admin_create_user(payload: AdminCreateUserRequest, _admin: dict = Depends(require_role("admin"))) -> dict:
    if payload.rol not in ROLES_HIERARCHY:
        raise HTTPException(status_code=400, detail=f"Rol inválido. Roles válidos: {sorted(ROLES_HIERARCHY)}")

    try:
        validar_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing = execute_query(
        "SELECT id FROM users WHERE email = %s OR phone = %s",
        (payload.email, payload.phone),
    )
    if existing:
        raise HTTPException(status_code=400, detail="El email o teléfono ya está registrado")

    pwd_hash = hash_password(payload.password)
    user_id = execute_query(
        "INSERT INTO users (name, cc, email, password, phone, position, proyecto) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (payload.name, payload.phone, payload.email, pwd_hash, payload.phone, f"Rol: {payload.rol}", "LOCAL"),
        fetch=False,
        return_lastrowid=True,
    )

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
    _auditar(_admin.get("id"), "crear_usuario", "user", user_id, f"rol={payload.rol}")
    return {"success": True, "user_id": user_id, "rol": payload.rol}


@router.post("/auth/refresh", tags=["Auth"])
async def refresh(payload: RefreshRequest) -> dict:
    """Rota un refresh token: devuelve un access token nuevo (8h) + refresh nuevo."""
    from src.presentation.auth import _buscar_usuario_por_id

    rotado = rotar_refresh_token(payload.refresh_token)
    if not rotado:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido o expirado")
    user_id, nuevo_refresh = rotado
    user = _buscar_usuario_por_id(user_id)
    if not user or not user.get("activo"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo")
    access = create_access_token({
        "sub": str(user["id"]),
        "telefono": user["telefono"],
        "rol": user["rol"],
        "nombre": user["nombre"],
        "email": user.get("email"),
    })
    return {"access_token": access, "refresh_token": nuevo_refresh, "token_type": "bearer"}


@router.post("/auth/forgot-password", tags=["Auth"])
async def forgot_password(payload: ForgotPasswordRequest) -> dict:
    """Inicia la recuperación: genera un token de un solo uso (30 min).

    Responde siempre igual para no revelar si la cuenta existe. Sin SMTP
    configurado, el token se entrega al solicitante solo fuera de producción
    (en producción queda en el log para que un admin lo retransmita).
    """
    from src.presentation.auth import _buscar_usuario_por_login

    user = _buscar_usuario_por_login(payload.identificador.strip())
    token_visible = None
    if user:
        try:
            raw = emitir_reset_token(user["id"])
            log.info("Reset token emitido para user %s", user["id"])
            _auditar(None, "solicitud_reset", "user", user["id"], None)
            if (settings.ENV or "").lower() != "production":
                token_visible = raw
            else:
                log.warning("Reset token user %s (retransmitir por canal interno)", user["id"])
        except Exception:
            log.exception("Error emitiendo reset token")
    resp = {"success": True, "mensaje": "Si la cuenta existe, se generó un token de recuperación."}
    if token_visible:
        resp["reset_token"] = token_visible
    return resp


@router.post("/auth/reset-password", tags=["Auth"])
async def reset_password(payload: ResetPasswordRequest) -> dict:
    """Consume un token de recuperación y fija la nueva contraseña."""
    try:
        validar_password(payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    user_id = consumir_reset_token(payload.token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")
    execute_query(
        "UPDATE users SET password = %s WHERE id = %s",
        (hash_password(payload.new_password), user_id),
        fetch=False,
    )
    revocar_refresh_tokens(user_id)
    log.info("Contraseña restablecida para user %s", user_id)
    _auditar(None, "reset_password", "user", user_id, None)
    return {"success": True, "mensaje": "Contraseña actualizada. Inicia sesión nuevamente."}


@router.get("/auth/auditoria", tags=["Auth"])
async def list_auditoria(
    limite: int = Query(50, ge=1, le=200),
    _admin: dict = Depends(require_role("admin")),
) -> dict:
    rows = execute_query(
        """SELECT id, actor_id, accion, objetivo_tipo, objetivo_id, detalle, created_at
           FROM auditoria_admin ORDER BY id DESC LIMIT %s""",
        (limite,),
    )
    for r in rows or []:
        if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
            r["created_at"] = r["created_at"].isoformat()
    return {"eventos": rows or []}
