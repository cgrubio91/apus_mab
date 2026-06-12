from abc import ABC, abstractmethod
from typing import Optional


class AIProvider(ABC):

    @abstractmethod
    def generate_text(self, prompt: str, system: Optional[str] = None, timeout: int = 120) -> str:
        ...

    @abstractmethod
    def extract_structured(self, prompt: str, document_text: str, schema: dict, timeout: int = 300) -> list:
        ...

    @abstractmethod
    def extract_from_pdf_multimodal(self, pdf_base64: str, filename: str, prompt: str, schema: dict, timeout: int = 600) -> list:
        ...
