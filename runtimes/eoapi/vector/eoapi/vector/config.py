"""API settings."""

from typing import List
from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    """API settings"""

    name: str = "eoAPI-vector"
    schemas: List[str] = ["pgstac", "public"]
    cors_origins: List[str] = ["*"]
    cors_methods: List[str] = ["GET"]
    cachecontrol: str = "public, max-age=3600"
    debug: bool = False
    root_path: str = ""

    catalog_ttl: int = 300

    model_config = {
        "env_prefix": "EOAPI_VECTOR_",
        "env_file": ".env",
        "extra": "allow",
    }
