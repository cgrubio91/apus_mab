"""
Tests de regresión de seguridad:
- El registro público nunca puede asignar un rol distinto de "user".
- Los endpoints de negocio exigen autenticación (401 sin token).
No requieren base de datos (se usa monkeypatch para las escrituras).
"""

import pytest
from fastapi.testclient import TestClient

from src.presentation.main import app
import src.presentation.routers.auth as auth_router


@pytest.fixture()
def client():
    # raise_server_exceptions=False para que fallos de DB en el lifespan no rompan
    # estos tests, que solo validan la capa de autenticación.
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestRegisterPrivilegeEscalation:
    def test_register_ignora_rol_admin(self, client, monkeypatch):
        """Aunque el payload incluya rol=admin, el usuario se crea como 'user'."""
        llamadas = []

        def fake_execute_query(query, params=None, fetch=True):
            llamadas.append((query, params))
            if query.strip().upper().startswith("SELECT"):
                return []  # el teléfono no existe aún
            return None

        monkeypatch.setattr(auth_router, "execute_query", fake_execute_query)

        res = client.post(
            "/api/v1/auth/register",
            json={"telefono": "300000", "nombre": "Atacante", "password": "secreta123", "rol": "admin"},
        )
        assert res.status_code == 200

        inserts = [(q, p) for q, p in llamadas if q.strip().upper().startswith("INSERT")]
        assert len(inserts) == 1
        _, params = inserts[0]
        assert "admin" not in params
        assert "user" in params

    def test_crear_usuario_admin_requiere_token(self, client):
        res = client.post(
            "/api/v1/auth/users",
            json={"telefono": "300000", "nombre": "X", "password": "secreta123", "rol": "admin"},
        )
        assert res.status_code == 401

    def test_listar_usuarios_requiere_token(self, client):
        assert client.get("/api/v1/auth/users").status_code == 401


class TestEndpointsRequierenAuth:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/v1/apus"),
            ("get", "/api/v1/dashboard"),
            ("get", "/api/v1/jobs"),
            ("post", "/api/v1/chat-assistant"),
            ("post", "/api/v1/save-extracted"),
            ("get", "/api/v1/analisis-apu"),
            ("post", "/api/v1/analisis-apu/1/analizar"),
        ],
    )
    def test_sin_token_devuelve_401(self, client, method, path):
        res = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
        assert res.status_code == 401

    def test_token_invalido_devuelve_401(self, client):
        res = client.get("/api/v1/apus", headers={"Authorization": "Bearer token-falso"})
        assert res.status_code == 401

    def test_login_sigue_siendo_publico(self, client, monkeypatch):
        import src.presentation.routers.auth as ar
        monkeypatch.setattr(ar, "execute_query", lambda *a, **k: [])
        res = client.post("/api/v1/auth/login", json={"telefono": "x", "password": "y"})
        assert res.status_code == 401  # credenciales inválidas, pero el endpoint es accesible
