from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # AI Provider
    AI_PROVIDER: str = "gemini"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:7b"

    # Auth
    JWT_SECRET_KEY: Optional[str] = None
    JWT_EXPIRE_MINUTES: int = 480

    # Database (MySQL)
    DB_HOST: Optional[str] = None
    DB_PORT: int = 3306
    DB_NAME: Optional[str] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_SSLMODE: str = "prefer"
    DB_POOL_MIN: int = 1
    DB_POOL_MAX: int = 10
    CLOUD_SQL_CONNECTION_NAME: Optional[str] = None

    # Twilio (WhatsApp)
    ACCOUNT_SID: Optional[str] = None
    AUTH_TOKEN: Optional[str] = None
    FROM_WHATSAPP: Optional[str] = None

    # Server
    PORT: int = 10000
    CORS_ORIGINS: str = "*"
    ENV: str = "development"

    # File limits
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MB

    # Extraction
    MAX_DOC_CHARS: int = 500_000


settings = Settings()

if settings.ENV.lower() == "production" and not settings.JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY es obligatoria en producción. Defínela en el entorno o .env.")
