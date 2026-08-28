from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SQLITE_DEFAULT = "sqlite:///./rag_eval.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(default=SQLITE_DEFAULT, alias="DATABASE_URL")
    api_key: str | None = Field(default=None, alias="RAG_EVAL_API_KEY")
    host: str = Field(default="127.0.0.1", alias="RAG_EVAL_HOST")
    port: int = Field(default=8000, alias="RAG_EVAL_PORT")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def blank_url_is_sqlite(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return SQLITE_DEFAULT
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
