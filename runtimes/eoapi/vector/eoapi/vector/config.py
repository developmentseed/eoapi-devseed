"""API settings."""

from pydantic import field_validator
from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    """API settings"""

    name: str = "eoAPI-vector"
    cors_origins: str = "*"
    cors_methods: str = "GET"
    cachecontrol: str = "public, max-age=3600"
    debug: bool = False
    root_path: str = ""

    catalog_ttl: int = 300

    model_config = {
        "env_prefix": "EOAPI_VECTOR_",
        "env_file": ".env",
        "extra": "allow",
    }

    @field_validator("cors_origins")
    def parse_cors_origin(cls, v):
        """Parse CORS origins."""
        return [origin.strip() for origin in v.split(",")]

    @field_validator("cors_methods")
    def parse_cors_methods(cls, v):
        """Parse CORS methods."""
        return [method.strip() for method in v.split(",")]
