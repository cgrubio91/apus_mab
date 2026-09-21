"""
Tests de la generación de la propuesta en segundo plano: el job guarda el
resultado, notifica el desenlace y se puede recuperar por solicitud.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.application.use_cases import constructor_job


@pytest.fixture
def espias(monkeypatch):
    """Sustituye job_manager y las notificaciones por espías en memoria."""
    estado = {"resultado": None, "error": None, "fases": [], "notificaciones": []}

    class JobManagerFalso:
        def update_phase(self, job_id, fase, **kw):
            estado["fases"].append(fase)

        def set_result(self, job_id, result):
            estado["resultado"] = result

        def set_error(self, job_id, error):
            estado["error"] = error

    monkeypatch.setattr(constructor_job, "job_manager", JobManagerFalso())
    monkeypatch.setattr(
        constructor_job, "crear_notificacion",
        lambda **kw: estado["notificaciones"].append(kw),
    )
    return estado


def test_nombre_del_job_permite_recuperar_la_solicitud():
    """El id de solicitud viaja en el nombre del job para retomarlo tras recargar."""
    nombre = constructor_job.nombre_job(231)
    assert constructor_job.solicitud_de_job(nombre) == 231
    assert constructor_job.solicitud_de_job("otro-archivo.pdf") is None
    assert constructor_job.solicitud_de_job(None) is None


def test_propuesta_lista_guarda_resultado_y_notifica(espias, monkeypatch):
    propuesta = {"propuesta": {"insumos": [{"descripcion": "Bordillo"}, {"descripcion": "Arena"}]}}
    monkeypatch.setattr(constructor_job.constructor_apu, "sugerir_estructura",
                        lambda sid, porcentajes_aiu=None: propuesta)

    devuelto = constructor_job.generar_propuesta_en_job(
        "job-1", 231, rol_destino="analista", actividad="Bordillo A80")

    # submit_job descarta el retorno: el resultado tiene que quedar en el job.
    assert espias["resultado"] == propuesta
    assert devuelto == propuesta

    assert len(espias["notificaciones"]) == 1
    noti = espias["notificaciones"][0]
    assert noti["rol_destino"] == "analista"
    assert "#231" in noti["titulo"]
    assert "2 insumo(s)" in noti["mensaje"]
    assert noti["solicitud_id"] == 231


def test_fallo_de_la_ia_notifica_y_propaga(espias, monkeypatch):
    """Si la IA falla hay que avisar igual: el usuario pudo salir de la pantalla."""
    def explota(sid, porcentajes_aiu=None):
        raise RuntimeError("Gemini saturado")

    monkeypatch.setattr(constructor_job.constructor_apu, "sugerir_estructura", explota)

    with pytest.raises(RuntimeError):
        constructor_job.generar_propuesta_en_job("job-2", 231, actividad="Bordillo A80")

    assert espias["resultado"] is None
    assert len(espias["notificaciones"]) == 1
    assert "No se pudo generar" in espias["notificaciones"][0]["titulo"]


def test_notificacion_no_se_duplica_al_relanzar(espias, monkeypatch):
    """La clave única evita llenar la campana si se regenera el mismo borrador."""
    monkeypatch.setattr(constructor_job.constructor_apu, "sugerir_estructura",
                        lambda sid, porcentajes_aiu=None: {"propuesta": {"insumos": []}})

    constructor_job.generar_propuesta_en_job("job-3", 231)
    constructor_job.generar_propuesta_en_job("job-4", 231)

    claves = {n["clave_unica"] for n in espias["notificaciones"]}
    assert claves == {"constructor:231:ok"}
