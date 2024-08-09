"""eoapi.stac app."""

import logging
from contextlib import asynccontextmanager

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

from . import auth, config, extension, logs

try:
    from importlib.resources import files as resources_files  # type: ignore
except ImportError:
    # Try backported to PY<39 `importlib_resources`.
    from importlib_resources import files as resources_files  # type: ignore


templates = Jinja2Templates(directory=str(resources_files(__package__) / "templates"))  # type: ignore

api_settings = config.ApiSettings()
auth_settings = auth.AuthSettings()
settings = Settings(enable_response_models=True)

# Logs
logs.init_logging(debug=api_settings.debug)
logger = logging.getLogger(__name__)

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
    "titiler": extension.TiTilerExtension(
        titiler_endpoint=api_settings.titiler_endpoint
    ),
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
    logger.debug("Connecting to DB...")
    await connect_to_db(app)
    yield
    # Close the Connection Pool
    logger.debug("Disconnecting from DB...")
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


if auth_settings.openid_configuration_url:
    oidc_auth = auth.OidcAuth(
        # URL to the OpenID Connect discovery document (https://openid.net/specs/openid-connect-discovery-1_0.html)
        openid_configuration_url=auth_settings.openid_configuration_url,
        openid_configuration_internal_url=auth_settings.openid_configuration_internal_url,
        # Optionally validate the "aud" claim in the JWT
        allowed_jwt_audiences=auth_settings.allowed_jwt_audiences,
        # To render scopes form on Swagger UI's login pop-up, populate with mapping of scopes to descriptions
        oauth2_supported_scopes={},
    )
    restricted_prefixes_methods = {
        "/collections": [
            "POST",
            "PUT",
            "DELETE",
            *([] if auth_settings.public_reads else ["GET"]),
        ],
        "/search": [] if auth_settings.public_reads else ["POST", "GET"],
    }
    for route in app.routes:
        restricted = any(
            route.path.startswith(f"{app.root_path}{prefix}")
            and set(route.methods).intersection(set(restricted_methods))
            for prefix, restricted_methods in restricted_prefixes_methods.items()
        )
        if restricted:
            oidc_auth.apply_auth_dependencies(route, required_token_scopes=[])
