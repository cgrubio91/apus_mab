"""
Integration tests for MAPUS API endpoints.
Requires a running PostgreSQL database (set TEST_DB_* env vars).
Automatically skipped when no database is available.
"""

import pytest
from fastapi.testclient import TestClient


class TestHealth:
    def test_health_endpoint(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"

    def test_root_endpoint(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "online"


class TestApusEndpoints:
    def test_get_apus_default(self, client: TestClient):
        resp = client.get("/api/apus")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] >= 3
        assert data["total"] >= 3

    def test_get_apus_with_filters(self, client: TestClient):
        resp = client.get("/api/apus?ciudad=Bogotá")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        for apu in data["data"]:
            assert "Bogotá" in apu.get("ciudad", "")

    def test_get_apus_pagination(self, client: TestClient):
        resp = client.get("/api/apus?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["limit"] == 1

    def test_get_apus_sort(self, client: TestClient):
        resp = client.get("/api/apus?sort_by=precio_unitario&sort_order=desc")
        assert resp.status_code == 200
        data = resp.json()
        prices = [apu["precio_unitario"] for apu in data["data"] if apu["precio_unitario"]]
        assert prices == sorted(prices, reverse=True)

    def test_get_apus_search(self, client: TestClient):
        resp = client.get("/api/apus?search=Excavación")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1


class TestApusV1Endpoints:
    def test_get_apus_v1(self, client: TestClient):
        resp = client.get("/api/v1/apus")
        assert resp.status_code == 200

    def test_get_filter_options_v1(self, client: TestClient):
        resp = client.get("/api/v1/apus/filter-options")
        assert resp.status_code == 200
        data = resp.json()
        assert "ciudad" in data
        assert "tipo_insumo" in data
        assert "Bogotá" in data["ciudad"]

    def test_get_projects_v1(self, client: TestClient):
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        project_names = [p["nombre_proyecto"] for p in data]
        assert "Proyecto Test Alpha" in project_names
        assert "Proyecto Test Gamma" in project_names


class TestDashboard:
    def test_dashboard_stats(self, client: TestClient):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_apus"] >= 3
        assert data["total_projects"] >= 2
        assert data["total_cities"] >= 2
        assert "apus_por_tipo_insumo" in data


class TestChatEndpoint:
    def test_chat_invalid_message(self, client: TestClient):
        resp = client.post("/api/chat-assistant", json={"message": ""})
        assert resp.status_code == 422

    def test_chat_valid_request(self, client: TestClient):
        resp = client.post(
            "/api/chat-assistant",
            json={"message": "¿Cuántos proyectos hay?", "telefono": "test-user", "nombre": "Test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data


class TestJobEndpoints:
    def test_list_jobs_empty(self, client: TestClient):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_job_not_found(self, client: TestClient):
        resp = client.get("/api/jobs/nonexistent-job-id")
        assert resp.status_code == 404


class TestAnalisisEndpoints:
    def test_list_solicitudes(self, client: TestClient):
        resp = client.get("/api/analisis-apu/solicitudes")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_solicitud_not_found(self, client: TestClient):
        resp = client.get("/api/analisis-apu/solicitudes/99999")
        assert resp.status_code == 404
