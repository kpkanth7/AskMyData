from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"), extra="ignore")

    app_name: str = Field(default="askmydata", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    app_mode: str = Field(default="safe", alias="APP_MODE")
    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    max_total_files: int = Field(default=5, alias="MAX_TOTAL_FILES")
    max_file_size_mb: int = Field(default=10, alias="MAX_FILE_SIZE_MB")

    default_llm_provider: str = Field(default="cerebras", alias="DEFAULT_LLM_PROVIDER")
    default_llm_model: str = Field(default="qwen-3-235b-a22b-instruct-2507", alias="DEFAULT_LLM_MODEL")
    fallback_llm_provider: str = Field(default="ollama", alias="FALLBACK_LLM_PROVIDER")
    fallback_llm_model: str = Field(default="llama3.1", alias="FALLBACK_LLM_MODEL")
    enable_llm_fallback: bool = Field(default=False, alias="ENABLE_LLM_FALLBACK")

    cerebras_api_key: str = Field(default="", alias="CEREBRAS_API_KEY")
    cerebras_model: str = Field(default="qwen-3-235b-a22b-instruct-2507", alias="CEREBRAS_MODEL")
    cerebras_base_url: str = Field(default="https://api.cerebras.ai/v1", alias="CEREBRAS_BASE_URL")

    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1", alias="OLLAMA_MODEL")
    ollama_timeout_seconds: int = Field(default=60, alias="OLLAMA_TIMEOUT_SECONDS")

    database_url: str = Field(default="", alias="DATABASE_URL")
    sqlite_default_path: str = Field(default="", alias="SQLITE_DEFAULT_PATH")

    enable_sql_preview: bool = Field(default=True, alias="ENABLE_SQL_PREVIEW")
    enable_charts: bool = Field(default=True, alias="ENABLE_CHARTS")
    enable_light_cleaning_prompt: bool = Field(default=True, alias="ENABLE_LIGHT_CLEANING_PROMPT")
    enable_multi_source_routing: bool = Field(default=True, alias="ENABLE_MULTI_SOURCE_ROUTING")
    enable_join_confirmation: bool = Field(default=True, alias="ENABLE_JOIN_CONFIRMATION")
    enable_dev_mode_tools: bool = Field(default=False, alias="ENABLE_DEV_MODE_TOOLS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def parsed_cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_dev_mode(self) -> bool:
        return self.app_mode.lower() == "dev" or self.enable_dev_mode_tools


@lru_cache
def get_settings() -> Settings:
    return Settings()
