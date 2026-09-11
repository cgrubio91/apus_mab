"""
Tests de recuperación de contraseña, refresh tokens y política de claves.
No requieren base de datos: se simula execute_query en memoria.
"""

import pytest
from fastapi.testclient import TestClient

import src.presentation.auth as auth_core
import src.presentation.routers.auth as auth_router
from src.config.settings import settings
from src.presentation.main import app


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class FakeDB:
    """Simula las tablas users, password_resets y refresh_tokens en memoria."""

    def __init__(self):
        self.users = {
            7: {"id": 7, "telefono": "3001112222", "nombre": "Prueba",
                "email": "prueba@x.com", "password": "hash-viejo",
                "roles_str": "user", "activo": 1},
        }
        self.resets = []
        self.refreshes = []
        self.seq = 100

    def __call__(self, query, params=None, **kwargs):
        q = " ".join(query.split())
        upper = q.upper()
        if upper.startswith("SELECT"):
            if "FROM PASSWORD_RESETS" in upper:
                h = params[0]
                return [dict(r) for r in self.resets if r["token_hash"] == h]
            if "FROM REFRESH_TOKENS" in upper:
                h = params[0]
                return [dict(r) for r in self.refreshes if r["token_hash"] == h]
            if "FROM USERS" in upper and "COUNT(*)" in upper:
                return [{"total": len(self.users)}]
            if "FROM USERS" in upper:
                if params and "WHERE U.ID" in upper or "WHERE ID" in upper:
                    uid = params[0]
                    u = self.users.get(uid)
                    return [dict(u)] if u else []
                ident = params[0] if params else None
                for u in self.users.values():
                    if u["email"] == ident or u["telefono"] == ident:
                        return [dict(u)]
                return []
            if "FROM AUDITORIA_ADMIN" in upper:
                return []
            if "FROM ROL" in upper:
                return [{"id": 13}]
            return []
        if upper.startswith("INSERT"):
            if "INTO PASSWORD_RESETS" in upper:
                self.seq += 1
                self.resets.append({"id": self.seq, "user_id": params[0],
                                    "token_hash": params[1], "expires_at": params[2],
                                    "used_at": None})
                return self.seq if kwargs.get("return_lastrowid") else None
            if "INTO REFRESH_TOKENS" in upper:
                self.seq += 1
                self.refreshes.append({"id": self.seq, "user_id": params[0],
                                       "token_hash": params[1], "expires_at": params[2],
                                       "revoked": 0})
                return self.seq if kwargs.get("return_lastrowid") else None
            if "INTO AUDITORIA_ADMIN" in upper:
                return None
            return 1 if kwargs.get("return_lastrowid") else None
        if upper.startswith("UPDATE"):
            if "PASSWORD_RESETS SET USED_AT" in upper:
                for r in self.resets:
                    if r["id"] == params[1]:
                        r["used_at"] = params[0]
                return None
            if "REFRESH_TOKENS SET REVOKED" in upper:
                if "WHERE ID" in upper:
                    for r in self.refreshes:
                        if r["id"] == params[0]:
                            r["revoked"] = 1
                else:
                    for r in self.refreshes:
                        if r["user_id"] == params[0]:
                            r["revoked"] = 1
                return None
            if "USERS SET PASSWORD" in upper:
                self.users[params[1]]["password"] = params[0]
                return None
            return None
        return None


@pytest.fixture()
def fakedb(monkeypatch):
    from src.presentation.middleware import _rate_store

    db = FakeDB()
    monkeypatch.setattr(auth_router, "execute_query", db)
    monkeypatch.setattr(auth_core, "execute_query", db)
    monkeypatch.setattr(settings, "ENV", "development")
    _rate_store._store.clear()
    return db


class TestPoliticaPassword:
    def test_corta_rechazada(self):
        with pytest.raises(ValueError):
            auth_core.validar_password("Abc123")

    def test_sin_numero_rechazada(self):
        with pytest.raises(ValueError):
            auth_core.validar_password("SinNumeros")

    def test_valida_ok(self):
        assert auth_core.validar_password("Clave2026") is None


class TestForgotReset:
    def test_usuario_inexistente_responde_igual(self, client, fakedb):
        res = client.post("/api/v1/auth/forgot-password", json={"identificador": "nadie@x.com"})
        assert res.status_code == 200
        assert "reset_token" not in res.json()

    def test_flujo_completo(self, client, fakedb):
        r1 = client.post("/api/v1/auth/forgot-password", json={"identificador": "3001112222"})
        assert r1.status_code == 200
        token = r1.json().get("reset_token")
        assert token

        # Token de un solo uso: segundo intento con el mismo falla
        r2 = client.post("/api/v1/auth/reset-password",
                         json={"token": token, "new_password": "Nueva2026"})
        assert r2.status_code == 200
        assert fakedb.users[7]["password"] != "hash-viejo"
        r3 = client.post("/api/v1/auth/reset-password",
                         json={"token": token, "new_password": "Otra2026x"})
        assert r3.status_code == 400

    def test_reset_token_invalido(self, client, fakedb):
        res = client.post("/api/v1/auth/reset-password",
                          json={"token": "falso", "new_password": "Nueva2026"})
        assert res.status_code == 400

    def test_reset_clave_debil(self, client, fakedb):
        res = client.post("/api/v1/auth/reset-password",
                          json={"token": "x", "new_password": "corta"})
        assert res.status_code == 400


class TestRefresh:
    def test_rotacion_ok(self, client, fakedb, monkeypatch):
        rt = auth_core.emitir_refresh_token(7)
        res = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert res.status_code == 200
        body = res.json()
        assert body["access_token"] and body["refresh_token"] != rt
        # El anterior quedó revocado
        res2 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert res2.status_code == 401

    def test_refresh_falso_401(self, client, fakedb):
        res = client.post("/api/v1/auth/refresh", json={"refresh_token": "falso"})
        assert res.status_code == 401


class TestRateLimitNuevasRutas:
    def test_reglas_existen(self):
        from src.presentation.middleware import _match_rate_rule

        assert _match_rate_rule("/api/v1/auth/refresh") is not None
        assert _match_rate_rule("/api/v1/auth/forgot-password") is not None
        assert _match_rate_rule("/api/v1/auth/reset-password") is not None
        assert _match_rate_rule("/api/v1/auth/login") is not None
