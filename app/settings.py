from __future__ import annotations
from functools import lru_cache
from enum import Enum
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentTypes(str, Enum):
    DEBUG = "Debug"
    PROD = "Prod"


class DeployEnvironment(str, Enum):
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="crm_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # Core app
    app_name: str = Field(...)
    environment: EnvironmentTypes = Field(...)
    deployment_environment: DeployEnvironment = Field(...)

    # Geidea configuration
    geidea_public_key: str = Field(...)
    geidea_api_password: str = Field(...)
    geidea_api_base: str = Field(...)

    # Application URLs
    geidea_success_url: str = Field(...)
    geidea_cancel_url: str = Field(...)
    geidea_callback_url: str = Field(...)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
