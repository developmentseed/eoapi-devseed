from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, Dict, Optional, Sequence

import jwt
from fastapi import HTTPException, Security, security, status
from fastapi.security.base import SecurityBase
from pydantic_settings import BaseSettings
from stac_fastapi.api.app import StacApi


class AuthSettings(BaseSettings):
    jwks_url: Optional[str] = None

    # Swagger UI config for Authorization Code Flow
    client_id: Optional[str] = ""
    use_pkce: bool = True
    oauth2_token_url: Optional[str] = None
    oauth2_authorization_url: Optional[str] = None

    allowed_jwt_audiences: Optional[Sequence[str]] = []

    model_config = {
        "env_prefix": "EOAPI_AUTH_",
        "env_file": ".env",
        "extra": "allow",
    }


@dataclass
class JwtAuth:
    jwks_url: str
    allowed_jwt_audiences: Optional[Sequence[str]]

    oauth2_authorization_url: Optional[str] = None
    oauth2_token_url: Optional[str] = None
    oauth2_supported_scopes: Optional[Dict[str, str]] = None

    # Generated attributes
    auth_scheme: SecurityBase = field(init=False)
    jwks_client: jwt.PyJWKClient = field(init=False)
    valid_token_dependency: Callable[..., Any] = field(init=False)

    def __post_init__(self):
        self.auth_scheme = self.create_auth_scheme()
        self.jwks_client = jwt.PyJWKClient(self.jwks_url)
        self.valid_token_dependency = self.create_user_token_dependency()

    def create_auth_scheme(self):
        return (
            security.OAuth2AuthorizationCodeBearer(
                authorizationUrl=self.oauth2_authorization_url,
                tokenUrl=self.oauth2_token_url,
                scopes=self.oauth2_supported_scopes,
            )
            if all([self.oauth2_authorization_url, self.oauth2_token_url])
            else security.HTTPBearer()
        )

    def create_user_token_dependency(self):
        def user_token(
            token_str: Annotated[str, Security(self.auth_scheme)],
            required_scopes: security.SecurityScopes,
        ):
            # Parse & validate token
            try:
                payload = jwt.decode(
                    token_str,
                    self.jwks_client.get_signing_key_from_jwt(token_str).key,
                    algorithms=["RS256"],
                    audience=self.allowed_jwt_audiences,
                )
            except jwt.exceptions.InvalidTokenError as e:
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
