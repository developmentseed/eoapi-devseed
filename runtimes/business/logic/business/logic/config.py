"""Settings."""

from enum import Enum
from typing import Any

from pydantic_core.core_schema import FieldValidationInfo
from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings


class ModeEnum(str, Enum):
    development = "development"
    production = "production"
    testing = "testing"


class Settings(BaseSettings):
    """Settings"""

    mode: ModeEnum = ModeEnum.development
    postgres_user: str
    postgres_pass: str
    postgres_dbname: str
    postgres_host: str
    postgres_port: int
    async_database_uri: PostgresDsn | str = ""

    cors_origins: str = "*"
    cors_methods: str = "GET,POST,OPTIONS"
    cachecontrol: str = "public, max-age=3600"
    debug: bool = False
    root_path: str = ""

    model_config = {
        "env_file": ".env",
        "extra": "allow",
    }

    @field_validator("async_database_uri", mode="after")
    def assemble_db_connection(cls, v: str | None, info: FieldValidationInfo) -> Any:
        if isinstance(v, str):
            if v == "":
                return PostgresDsn.build(
                    scheme="postgresql+asyncpg",
                    username=info.data["postgres_user"],
                    password=info.data["postgres_pass"],
                    host=info.data["postgres_host"],
                    port=info.data["postgres_port"],
                    path=info.data["postgres_dbname"],
                )
        return v

    @field_validator("cors_origins")
    def parse_cors_origin(cls, v):
        """Parse CORS origins."""
        return [origin.strip() for origin in v.split(",")]

    @field_validator("cors_methods")
    def parse_cors_methods(cls, v):
        """Parse CORS methods."""
        return [method.strip() for method in v.split(",")]
