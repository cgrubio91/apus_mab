from abc import ABC, abstractmethod
from typing import Optional, List
from src.domain.entities.apu import ApuRecord


class ApuRepository(ABC):

    @abstractmethod
    def get_apus(
        self,
        filters: dict,
        limit: int = 50,
        offset: int = 0,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
        search: Optional[str] = None,
    ) -> dict:
        ...

    @abstractmethod
    def get_unique_projects(self) -> list[str]:
        ...

    @abstractmethod
    def get_dashboard_stats(self) -> dict:
        ...

    @abstractmethod
    def get_filter_options(self) -> dict[str, list[str]]:
        ...

    @abstractmethod
    def delete_project_apus(self, nombre_proyecto: str) -> dict:
        ...

    @abstractmethod
    def insert_apus_batch(self, apus_list: list) -> dict:
        ...

    @abstractmethod
    def insert_apus_stream(self, apus_list: list):
        ...
