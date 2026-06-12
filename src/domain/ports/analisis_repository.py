from abc import ABC, abstractmethod
from typing import Optional


class AnalisisRepository(ABC):

    @abstractmethod
    def crear_solicitud(self, grupos_insumos: list[dict]) -> int:
        ...

    @abstractmethod
    def get_solicitudes(self, estado: Optional[str] = None) -> list:
        ...

    @abstractmethod
    def get_solicitud(self, solicitud_id: int) -> Optional[dict]:
        ...

    @abstractmethod
    def guardar_analisis(self, solicitud_id: int, analisis_json: str, resumen: str, recomendacion: str):
        ...

    @abstractmethod
    def actualizar_estado(self, solicitud_id: int, estado: str) -> bool:
        ...

    @abstractmethod
    def insertar_historial(self, solicitud_id: int, accion: str, rol: str, nombre: str, motivo: Optional[str] = None):
        ...

    @abstractmethod
    def insertar_aprendizaje(self, analisis_id: int, motivo: str, contexto: str):
        ...

    @abstractmethod
    def get_aprendizaje_rechazos(self, limit: int = 20) -> list:
        ...
