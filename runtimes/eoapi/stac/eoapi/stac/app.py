"""eoapi.stac app."""

from contextlib import asynccontextmanager

from eoapi.stac.auth import AuthSettings, JwtAuth
from eoapi.stac.config import ApiSettings
from eoapi.stac.extension import TiTilerExtension
from fastapi import FastAPI
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
auth_settings = AuthSettings()
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
        swagger_ui_init_oauth={
            "clientId": auth_settings.client_id,
            "usePkceWithAuthorizationCodeGrant": auth_settings.use_pkce,
        },
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


if auth_settings.jwks_url:
    JwtAuth(
        # JWT Validation configuration
        jwks_url=auth_settings.jwks_url,
        allowed_jwt_audiences=auth_settings.allowed_jwt_audiences,
        # Authorization Code Flow configuration
        oauth2_authorization_url=auth_settings.oauth2_authorization_url,
        oauth2_token_url=auth_settings.oauth2_token_url,
        # To render scopes form on Swagger UI's login pop-up, populate with mapping of scopes to descriptions
        oauth2_supported_scopes={},
    ).require_auth(
        api=api,
        routes={
            f"{app.root_path}/{route}": ["POST", "PUT", "DELETE"]
            for route in [
                "collections",
                "collections/{collectionId}",
                "collections/{collectionId}/items",
                "collections/{collectionId}/bulk_items",
                "collections/{collectionId}/items/{itemId}",
            ]
        },
        required_scopes=[],
    )
