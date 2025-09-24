"""eoapi.vector app."""

import logging
from contextlib import asynccontextmanager
from importlib.resources import files as resources_files

import jinja2
from eoapi.auth_utils import OpenIdConnectAuth, OpenIdConnectSettings
from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware
from starlette.templating import Jinja2Templates
from starlette_cramjam.middleware import CompressionMiddleware
from tipg.collections import register_collection_catalog
from tipg.database import close_db_connection, connect_to_db
from tipg.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from tipg.factory import Endpoints as TiPgEndpoints
from tipg.middleware import CacheControlMiddleware, CatalogUpdateMiddleware
from tipg.openapi import _update_openapi
from tipg.settings import DatabaseSettings

from . import __version__ as eoapi_vector_version
from .config import ApiSettings, PostgresSettings
from .logs import init_logging

CUSTOM_SQL_DIRECTORY = resources_files(__package__) / "sql"

settings = ApiSettings()
auth_settings = OpenIdConnectSettings()
db_settings = DatabaseSettings(
    # For the Tables' Catalog we only use the `public` schema
    schemas=["public"],
    # We exclude public functions
    exclude_function_schemas=["public"],
    # We allow non-spatial tables
    spatial=False,
)


# Logs
init_logging(debug=settings.debug)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan."""
    logger.debug("Connecting to db...")
    await connect_to_db(
        app,
        # We enable both pgstac and public schemas (pgstac will be used by custom functions)
        schemas=["pgstac", "public"],
        user_sql_files=list(CUSTOM_SQL_DIRECTORY.glob("*.sql")),  # type: ignore
        settings=PostgresSettings(),
    )

    logger.debug("Registering collection catalog...")
    await register_collection_catalog(app, db_settings=db_settings)

    yield

    # Close the Connection Pool
    logger.debug("Closing db connections...")
    await close_db_connection(app)


app = FastAPI(
    title=settings.name,
    version=eoapi_vector_version,
    openapi_url="/api",
    docs_url="/api.html",
    lifespan=lifespan,
    root_path=settings.root_path,
    swagger_ui_init_oauth={
        "clientId": auth_settings.client_id,
        "usePkceWithAuthorizationCodeGrant": auth_settings.use_pkce,
    },
)

# Fix OpenAPI response header for OGC Common compatibility
_update_openapi(app)

# add eoapi_vector templates and tipg templates
jinja2_env = jinja2.Environment(
    loader=jinja2.ChoiceLoader(
        [
            jinja2.PackageLoader(__package__, "templates"),
            jinja2.PackageLoader("tipg", "templates"),
        ]
    )
)
templates = Jinja2Templates(env=jinja2_env)

# Register TiPg endpoints.
endpoints = TiPgEndpoints(
    title=settings.name,
    templates=templates,
    with_tiles_viewer=True,
)
app.include_router(endpoints.router)

# Set all CORS enabled origins
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=settings.cors_methods,
        allow_headers=["*"],
    )

app.add_middleware(CacheControlMiddleware, cachecontrol=settings.cachecontrol)
app.add_middleware(CompressionMiddleware)

if settings.catalog_ttl:
    app.add_middleware(
        CatalogUpdateMiddleware,
        func=register_collection_catalog,
        ttl=settings.catalog_ttl,
        db_settings=db_settings,
    )

add_exception_handlers(app, DEFAULT_STATUS_CODES)


@app.get(
    "/healthz",
    description="Health Check.",
    summary="Health Check.",
    operation_id="healthCheck",
    tags=["Health Check"],
)
def ping():
    """Health check."""
    from pyproj import __proj_version__ as proj_version  # noqa
    from pyproj import __version__ as pyproj_version  # noqa
    from tipg import __version__ as tipg_version  # noqa

    return {
        "versions": {
            "tipg": tipg_version,
            "proj": proj_version,
            "pyproj": pyproj_version,
        },
    }


if settings.debug:

    @app.get("/rawcatalog", include_in_schema=False)
    async def raw_catalog(request: Request):
        """Return parsed catalog data for testing."""
        return request.app.state.collection_catalog

    @app.get("/refresh", include_in_schema=False)
    async def refresh(request: Request):
        """Return parsed catalog data for testing."""
        await register_collection_catalog(request.app, db_settings=db_settings)
        return request.app.state.collection_catalog


if auth_settings.openid_configuration_url:
    oidc_auth = OpenIdConnectAuth.from_settings(auth_settings)

    restricted_prefixes = ["/collections"]
    for route in app.routes:
        if any(
            route.path.startswith(f"{app.root_path}{prefix}")
            for prefix in restricted_prefixes
        ):
            oidc_auth.apply_auth_dependencies(route, required_token_scopes=[])
