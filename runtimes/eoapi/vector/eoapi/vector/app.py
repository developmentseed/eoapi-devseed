"""eoapi.vector app."""

from contextlib import asynccontextmanager

import jinja2
from eoapi.vector import __version__ as eoapi_vector_version
from eoapi.vector.auth import AuthSettings, OidcAuth
from eoapi.vector.config import ApiSettings
from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware
from starlette.templating import Jinja2Templates
from starlette_cramjam.middleware import CompressionMiddleware
from tipg.collections import register_collection_catalog
from tipg.database import close_db_connection, connect_to_db
from tipg.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from tipg.factory import Endpoints as TiPgEndpoints
from tipg.middleware import CacheControlMiddleware, CatalogUpdateMiddleware
from tipg.settings import PostgresSettings

try:
    from importlib.resources import files as resources_files  # type: ignore
except ImportError:
    # Try backported to PY<39 `importlib_resources`.
    from importlib_resources import files as resources_files  # type: ignore


CUSTOM_SQL_DIRECTORY = resources_files(__package__) / "sql"

settings = ApiSettings()
postgres_settings = PostgresSettings()
auth_settings = AuthSettings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan."""
    await connect_to_db(
        app,
        settings=postgres_settings,
        # We enable both pgstac and public schemas (pgstac will be used by custom functions)
        schemas=["pgstac", "public"],
        user_sql_files=list(CUSTOM_SQL_DIRECTORY.glob("*.sql")),  # type: ignore
    )
    await register_collection_catalog(
        app,
        # For the Tables' Catalog we only use the `public` schema
        schemas=["public"],
        # We exclude public functions
        exclude_function_schemas=["public"],
        # We allow non-spatial tables
        spatial=False,
    )

    yield

    # Close the Connection Pool
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
        schemas=["public"],
        exclude_function_schemas=["public"],
        spatial=False,
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
    return {"ping": "pong!"}


if settings.debug:

    @app.get("/rawcatalog", include_in_schema=False)
    async def raw_catalog(request: Request):
        """Return parsed catalog data for testing."""
        return request.app.state.collection_catalog

    @app.get("/refresh", include_in_schema=False)
    async def refresh(request: Request):
        """Return parsed catalog data for testing."""
        await register_collection_catalog(
            request.app,
            # For the Tables' Catalog we only use the `public` schema
            schemas=["public"],
            # We exclude public functions
            exclude_function_schemas=["public"],
            # We allow non-spatial tables
            spatial=False,
        )

        return request.app.state.collection_catalog


if auth_settings.openid_configuration_url and not auth_settings.public_reads:
    oidc_auth = OidcAuth(
        # URL to the OpenID Connect discovery document (https://openid.net/specs/openid-connect-discovery-1_0.html)
        openid_configuration_url=auth_settings.openid_configuration_url,
        openid_configuration_internal_url=auth_settings.openid_configuration_internal_url,
        # Optionally validate the "aud" claim in the JWT
        allowed_jwt_audiences=auth_settings.allowed_jwt_audiences,
        # To render scopes form on Swagger UI's login pop-up, populate with mapping of scopes to descriptions
        oauth2_supported_scopes={},
    )

    protected_prefixes = ["/collections"]
    for route in app.routes:
        if not any(
            route.path.startswith(f"{app.root_path}{prefix}")
            for prefix in protected_prefixes
        ):
            continue
        oidc_auth.apply_auth_dependencies(route, required_token_scopes=[])
