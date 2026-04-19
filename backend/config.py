"""
nexaagent/backend/config.py
Centralised settings loaded from .env. Validated by Pydantic on startup.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # App
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # Security
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_agent_token_expire_minutes: int = 480

    # PostgreSQL
    database_url: str = Field(...)

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 3600
    redis_session_ttl: int = 86400

    # Groq
    groq_api_key: str = Field(...)
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.3
    groq_max_tokens: int = 1024
    groq_timeout: int = 30

    # ChromaDB
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "nexaagent_kb"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_device: str = "cpu"

    # Escalation thresholds
    escalation_max_turns: int = 5
    kb_confidence_threshold: float = 0.50
    kb_auto_resolve_threshold: float = 0.85

    # Queue / SLA
    queue_key_prefix: str = "nexaagent:queue"
    ticket_channel_prefix: str = "nexaagent:tickets"
    max_agent_tickets: int = 10
    sla_critical_minutes: int = 15
    sla_high_minutes: int = 60
    sla_medium_minutes: int = 240
    sla_low_minutes: int = 1440

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def sla_minutes(self) -> dict:
        return {
            "CRITICAL": self.sla_critical_minutes,
            "HIGH": self.sla_high_minutes,
            "MEDIUM": self.sla_medium_minutes,
            "LOW": self.sla_low_minutes,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
