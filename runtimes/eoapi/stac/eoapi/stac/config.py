"""API settings."""

from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    """API settings"""

    name: str = "eoAPI-stac"
    cors_origins: str = "*"
    cors_methods: str = "GET,POST,OPTIONS"
    cachecontrol: str = "public, max-age=3600"
    debug: bool = False

    titiler_endpoint: Optional[str] = None

    extensions: List[str] = [
        "filter",
        "query",
        "sort",
        "fields",
        "pagination",
        "titiler",
        "transaction",
    ]

    @field_validator("cors_origins")
    def parse_cors_origin(cls, v):
        """Parse CORS origins."""
        return [origin.strip() for origin in v.split(",")]

    @field_validator("cors_methods")
    def parse_cors_methods(cls, v):
        """Parse CORS methods."""
        return [method.strip() for method in v.split(",")]

    model_config = {
        "env_prefix": "EOAPI_STAC_",
        "env_file": ".env",
        "extra": "allow",
    }
