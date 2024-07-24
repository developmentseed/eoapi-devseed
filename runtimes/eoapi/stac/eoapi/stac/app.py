"""eoapi.stac app."""

from contextlib import asynccontextmanager
from typing import Annotated

import jwt
from eoapi.stac.config import ApiSettings
from eoapi.stac.extension import TiTilerExtension
from fastapi import FastAPI, HTTPException, security, status
from fastapi.responses import ORJSONResponse
from stac_fastapi.api.app import StacApi
from stac_fastapi.api.models import (
    ItemCollectionUri,
    create_get_request_model,
    create_post_request_model,
    create_request_model,
)
from stac_fastapi.extensions.core import (
    FieldsExtension,
    FilterExtension,
    SortExtension,
    TokenPaginationExtension,
    TransactionExtension,
)
from stac_fastapi.extensions.third_party import BulkTransactionExtension
from stac_fastapi.pgstac.config import Settings
from stac_fastapi.pgstac.core import CoreCrudClient
from stac_fastapi.pgstac.db import close_db_connection, connect_to_db
from stac_fastapi.pgstac.extensions import QueryExtension
from stac_fastapi.pgstac.extensions.filter import FiltersClient
from stac_fastapi.pgstac.transactions import BulkTransactionsClient, TransactionsClient
from stac_fastapi.pgstac.types.search import PgstacSearch
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from starlette_cramjam.middleware import CompressionMiddleware

try:
    from importlib.resources import files as resources_files  # type: ignore
except ImportError:
    # Try backported to PY<39 `importlib_resources`.
    from importlib_resources import files as resources_files  # type: ignore


templates = Jinja2Templates(directory=str(resources_files(__package__) / "templates"))  # type: ignore

api_settings = ApiSettings()
settings = Settings(enable_response_models=True)

# Extensions
extensions_map = {
    "transaction": TransactionExtension(
        client=TransactionsClient(),
        settings=settings,
        response_class=ORJSONResponse,
    ),
    "query": QueryExtension(),
    "sort": SortExtension(),
    "fields": FieldsExtension(),
    "pagination": TokenPaginationExtension(),
    "filter": FilterExtension(client=FiltersClient()),
    "bulk_transactions": BulkTransactionExtension(client=BulkTransactionsClient()),
    "titiler": TiTilerExtension(titiler_endpoint=api_settings.titiler_endpoint),
}

if enabled_extensions := api_settings.extensions:
    extensions = [
        extensions_map.get(name)
        for name in enabled_extensions
        if name in extensions_map
    ]
else:
    extensions = list(extensions_map.values())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan."""
    # Create Connection Pool
    await connect_to_db(app)
    yield
    # Close the Connection Pool
    await close_db_connection(app)


# Middlewares
middlewares = [Middleware(CompressionMiddleware)]
if api_settings.cors_origins:
    middlewares.append(
        Middleware(
            CORSMiddleware,
            allow_origins=api_settings.cors_origins,
            allow_credentials=True,
            allow_methods=api_settings.cors_methods,
            allow_headers=["*"],
        )
    )

# Custom Models
items_get_model = ItemCollectionUri
if any(isinstance(ext, TokenPaginationExtension) for ext in extensions):
    items_get_model = create_request_model(
        model_name="ItemCollectionUri",
        base_model=ItemCollectionUri,
        mixins=[TokenPaginationExtension().GET],
        request_type="GET",
    )

search_get_model = create_get_request_model(extensions)
search_post_model = create_post_request_model(extensions, base_model=PgstacSearch)

api = StacApi(
    app=FastAPI(
        title=api_settings.name,
        lifespan=lifespan,
        openapi_url="/api",
        docs_url="/api.html",
        redoc_url=None,
    ),
    title=api_settings.name,
    description=api_settings.name,
    settings=settings,
    extensions=extensions,
    client=CoreCrudClient(post_request_model=search_post_model),
    items_get_request_model=items_get_model,
    search_get_request_model=search_get_model,
    search_post_request_model=search_post_model,
    response_class=ORJSONResponse,
    middlewares=middlewares,
)
app = api.app


@app.get("/index.html", response_class=HTMLResponse)
async def viewer_page(request: Request):
    """Search viewer."""
    return templates.TemplateResponse(
        request,
        name="stac-viewer.html",
        context={
            "endpoint": str(request.url).replace("/index.html", ""),
        },
        media_type="text/html",
    )


if settings.jwks_url:
    jwks_client = jwt.PyJWKClient(settings.jwks_url)  # Caches JWKS

    # Setup auth requirements
    oauth2_scheme = (
        security.OAuth2AuthorizationCodeBearer(
            authorizationUrl=f"{settings.oauth2_authorization_url}",
            tokenUrl=f"{settings.oauth2_token_url}",
            scopes={
                # NOTE: Add requested scopes here if needed...
            },
        )
        if (settings.oauth2_authorization_url and settings.oauth2_token_url)
        else security.HTTPAuthorizationCredentials()
    )

    def user_token(
        token_str: Annotated[str, security.Security(oauth2_scheme)],
        required_scopes: security.SecurityScopes,
    ):
        # Parse & validate token
        try:
            payload = jwt.decode(
                token_str,
                jwks_client.get_signing_key_from_jwt(token_str).key,
                algorithms=["RS256"],
                audience=settings.permitted_jwt_audiences,
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

    # Add dependency to all endpoints that create, modify or delete data.
    api.add_route_dependencies(
        [
            {
                "path": path,
                "method": method,
                "type": "http",
            }
            for method in ["POST", "PUT", "DELETE"]
            for path in [
                "/collections",
                "/collections/{collectionId}",
                "/collections/{collectionId}/items",
                "/collections/{collectionId}/bulk_items",
                "/collections/{collectionId}/items/{itemId}",
            ]
        ],
        [
            # NOTE: Add required scopes here if desired...
            security.Security(user_token, scopes=[])
        ],
    )
