"""eoapi.auth configuration."""

from typing import Optional, Sequence

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings


class AuthSettings(BaseSettings):
    """Swagger UI config for Authorization Code Flow"""

    client_id: str = ""
    use_pkce: bool = True
    openid_configuration_url: Optional[AnyHttpUrl] = None
    openid_configuration_internal_url: Optional[AnyHttpUrl] = None

    allowed_jwt_audiences: Optional[Sequence[str]] = []

    public_reads: bool = True

    model_config = {
        "env_prefix": "EOAPI_AUTH_",
        "env_file": ".env",
        "extra": "allow",
    }
