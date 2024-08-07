from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, Dict, Optional, Sequence
import logging
import urllib.request
import json

from fastapi import HTTPException, Security, security, status
from fastapi.security.base import SecurityBase
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings
from stac_fastapi.api.app import StacApi
import jwt

logger = logging.getLogger(__name__)


class AuthSettings(BaseSettings):
    # Swagger UI config for Authorization Code Flow
    client_id: str = ""
    use_pkce: bool = True
    openid_configuration_url: Optional[AnyHttpUrl] = None
    openid_configuration_internal_url: Optional[AnyHttpUrl] = None

    allowed_jwt_audiences: Optional[Sequence[str]] = []

    model_config = {
        "env_prefix": "EOAPI_AUTH_",
        "env_file": ".env",
        "extra": "allow",
    }


@dataclass
class OidcAuth:
    openid_configuration_url: AnyHttpUrl
    openid_configuration_internal_url: Optional[AnyHttpUrl] = None
    allowed_jwt_audiences: Optional[Sequence[str]] = None
    oauth2_supported_scopes: Dict[str, str] = field(default_factory=dict)

    # Generated attributes
    auth_scheme: SecurityBase = field(init=False)
    jwks_client: jwt.PyJWKClient = field(init=False)
    valid_token_dependency: Callable[..., Any] = field(init=False)

    def __post_init__(self):
        oidc_config_url = str(
            self.openid_configuration_internal_url or self.openid_configuration_url
        )
        with urllib.request.urlopen(oidc_config_url) as response:
            if response.status != 200:
                raise Exception(
                    f"Request for OIDC config failed with status {response.status}"
                )
            oidc_config = json.load(response)
        self.jwks_client = jwt.PyJWKClient(oidc_config["jwks_uri"])
        self.auth_scheme = security.OpenIdConnect(
            openIdConnectUrl=self.openid_configuration_url.unicode_string()
        )
        self.valid_token_dependency = self.create_user_token_dependency(
            auth_scheme=self.auth_scheme,
            jwks_client=self.jwks_client,
            allowed_jwt_audiences=self.allowed_jwt_audiences,
        )

    @staticmethod
    def create_user_token_dependency(
        auth_scheme: SecurityBase,
        jwks_client: jwt.PyJWKClient,
        allowed_jwt_audiences: Sequence[str],
    ):
        """
        Create a dependency that validates JWT tokens & scopes.
        """

        def user_token(
            token_str: Annotated[str, Security(auth_scheme)],
            required_scopes: security.SecurityScopes,
        ):
            token_parts = token_str.split(" ")
            if len(token_parts) != 2 or token_parts[0].lower() != "bearer":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authorization header",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                [_, token] = token_parts
            # Parse & validate token
            try:
                payload = jwt.decode(
                    token,
                    jwks_client.get_signing_key_from_jwt(token).key,
                    algorithms=["RS256"],
                    # NOTE: Audience validation MUST match audience claim if set in token (https://pyjwt.readthedocs.io/en/stable/changelog.html?highlight=audience#id40)
                    audience=allowed_jwt_audiences,
                )
            except jwt.exceptions.InvalidTokenError as e:
                logger.exception(f"InvalidTokenError: {e=}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from e

            # Validate scopes (if required)
            for scope in required_scopes.scopes:
                if scope not in payload["scope"]:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Not enough permissions",
                        headers={
                            "WWW-Authenticate": f'Bearer scope="{required_scopes.scope_str}"'
                        },
                    )

            return payload

        return user_token

    def require_auth(
        self,
        *,
        api: StacApi,
        routes: Dict[str, Sequence[str]],
        required_scopes: Optional[Sequence[str]],
    ):
        """
        Helper to add auth dependencies to existing routes.
        """
        api.add_route_dependencies(
            [
                {
                    "path": path,
                    "method": method,
                    "type": "http",
                }
                for path, methods in routes.items()
                for method in methods
            ],
            [Security(self.valid_token_dependency, scopes=required_scopes)],
        )
        return self
