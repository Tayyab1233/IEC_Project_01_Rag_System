"""Configuration settings for the Production RAG Service.

All settings are strictly managed via environment variables and .env files
using pydantic-settings.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration and pinned model definitions."""

    # Application & Environment
    APP_NAME: str = "Production RAG Service"
    APP_ENV: str = "development"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Security & Authentication
    JWT_SECRET: str = "default_insecure_jwt_secret_change_in_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # API Keys
    GEMINI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # Pinned Model IDs & Generation Parameters
    GENERATION_MODEL: str = "gemini-3.8-flash"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    FALLBACK_EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    TEMPERATURE: float = 0.1

    # Chunking & Ingestion Settings
    CHUNK_SIZE: int = 450
    CHUNK_OVERLAP: int = 60
    MAX_UPLOAD_MB: int = 20
    UPLOAD_DIR: str = "./uploads"

    # Retrieval & Search Thresholds
    RETRIEVAL_TOP_K: int = 18
    CONTEXT_CHUNKS: int = 15
    MIN_SIMILARITY: float = 0.25
    MIN_RELEVANCE_SCORE: float = 0.25
    RRF_K: int = 60

    # Guardrails & Safety Parameters
    MAX_QUESTION_CHARS: int = 1000
    API_TIMEOUT_SECONDS: int = 30
    RAM_THRESHOLD_GB: float = 6.5
    CANARY_TOKEN: str = "CANARY_CONFIDENTIAL_DO_NOT_EXFILTRATE"

    # Database & Storage
    DATABASE_URL: str = "sqlite+aiosqlite:///./rag_service.db"
    SYNC_DATABASE_URL: str = "sqlite:///./rag_service.db"
    QDRANT_PATH: str = "./qdrant_data"
    QDRANT_COLLECTION: str = "rag_chunks"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of the application settings."""
    return Settings()
