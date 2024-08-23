"""eoapi.vector app."""

import logging
from contextlib import asynccontextmanager

import jinja2
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

from . import __version__ as eoapi_vector_version
from . import config, logs

try:
    from importlib.resources import files as resources_files  # type: ignore
except ImportError:
    # Try backported to PY<39 `importlib_resources`.
    from importlib_resources import files as resources_files  # type: ignore


CUSTOM_SQL_DIRECTORY = resources_files(__package__) / "sql"

settings = config.ApiSettings()
postgres_settings = PostgresSettings()

# Logs
logs.init_logging(
    debug=settings.debug,
    loggers={
        "botocore.credentials": {
            "level": "CRITICAL",
            "propagate": False,
        },
        "botocore.utils": {
            "level": "CRITICAL",
            "propagate": False,
        },
        "rio-tiler": {
            "level": "ERROR",
            "propagate": False,
        },
    },
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan."""
    logger.debug("Connecting to db...")
    await connect_to_db(
        app,
        settings=postgres_settings,
        schemas=settings.schemas,
        user_sql_files=list(CUSTOM_SQL_DIRECTORY.glob("*.sql")),  # type: ignore
    )

    logger.debug("Registering collection catalog...")
    await register_collection_catalog(
        app,
        # For the Tables' Catalog we only use the `public` schema
        schemas=settings.schemas,
        # We exclude public functions
        exclude_function_schemas=["public"],
        # We allow non-spatial tables
        spatial=False,
    )

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
