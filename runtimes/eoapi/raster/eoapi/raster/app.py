"""eoAPI Raster application."""

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Dict, Literal, Optional

import jinja2
import pystac
import rasterio
from eoapi.auth_utils import OpenIdConnectAuth, OpenIdConnectSettings
from fastapi import Depends, FastAPI, Query
from psycopg import OperationalError
from psycopg.rows import dict_row
from psycopg_pool import PoolTimeout
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from starlette_cramjam.middleware import CompressionMiddleware
from titiler.core import __version__ as titiler_version
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.core.factory import (
    AlgorithmFactory,
    ColorMapFactory,
    MultiBaseTilerFactory,
    TilerFactory,
    TMSFactory,
)
from titiler.core.middleware import CacheControlMiddleware
from titiler.core.models.OGC import Conformance, Landing
from titiler.core.resources.enums import MediaType
from titiler.core.utils import accept_media_type, create_html_response, update_openapi
from titiler.extensions import cogViewerExtension
from titiler.mosaic.errors import MOSAIC_STATUS_CODES
from titiler.pgstac import __version__ as titiler_pgstac_version
from titiler.pgstac.db import close_db_connection, connect_to_db
from titiler.pgstac.dependencies import (
    AssetIdParams,
    CollectionIdParams,
    ItemIdParams,
    SearchIdParams,
)
from titiler.pgstac.extensions import searchInfoExtension
from titiler.pgstac.factory import (
    MosaicTilerFactory,
    add_search_list_route,
    add_search_register_route,
)
from titiler.pgstac.reader import PgSTACReader

from . import __version__ as eoapi_raster_version
from .config import ApiSettings, PostgresSettings
from .logs import init_logging

settings = ApiSettings()
auth_settings = OpenIdConnectSettings()


# Logs
init_logging(
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


logger.debug("Loading jinja2 templates...")
jinja2_env = jinja2.Environment(
    autoescape=jinja2.select_autoescape(["html", "xml"]),
    loader=jinja2.ChoiceLoader(
        [
            jinja2.PackageLoader(__package__, "templates"),
            jinja2.PackageLoader("titiler.core", "templates"),
        ]
    ),
)
templates = Jinja2Templates(env=jinja2_env)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan."""
    logger.debug("Connecting to db...")
    await connect_to_db(app, settings=PostgresSettings())
    logger.debug("Connected to db.")

    yield

    logger.debug("Closing db connections...")
    await close_db_connection(app)
    logger.debug("Closed db connection.")


app = FastAPI(
    title=settings.name,
    version=eoapi_raster_version,
    openapi_url="/api",
    docs_url="/api.html",
    root_path=settings.root_path,
    lifespan=lifespan,
    swagger_ui_init_oauth={
        "clientId": auth_settings.client_id,
        "usePkceWithAuthorizationCodeGrant": auth_settings.use_pkce,
    },
)

# Fix OpenAPI response header for OGC Common compatibility
update_openapi(app)

add_exception_handlers(app, DEFAULT_STATUS_CODES)
add_exception_handlers(app, MOSAIC_STATUS_CODES)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=settings.cors_methods,
        allow_headers=["*"],
    )

app.add_middleware(
    CacheControlMiddleware,
    cachecontrol=settings.cachecontrol,
    exclude_path={r"/healthz", r"/collections"},
)
app.add_middleware(
    CompressionMiddleware,
    exclude_mediatype={
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/jp2",
        "image/webp",
    },
)

TITILER_CONFORMS_TO = {
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/landing-page",
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/html",
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/json",
}


###############################################################################
# `Secret` endpoint for mosaic builder. Do not need to be public (in the OpenAPI docs)
@app.get("/collections", include_in_schema=False)
async def list_collection(request: Request):
    """list collections."""
    with request.app.state.dbpool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM pgstac.all_collections();")
            r = cursor.fetchone()
            return r.get("all_collections", [])


###############################################################################
# STAC Search Endpoints
searches = MosaicTilerFactory(
    path_dependency=SearchIdParams,
    router_prefix="/searches/{search_id}",
    add_statistics=True,
    add_viewer=True,
    add_part=True,
    extensions=[
        searchInfoExtension(),
    ],
    templates=templates,
)
app.include_router(
    searches.router, tags=["STAC Search"], prefix="/searches/{search_id}"
)

add_search_register_route(
    app,
    prefix="/searches",
    tile_dependencies=[
        searches.layer_dependency,
        searches.dataset_dependency,
        searches.pixel_selection_dependency,
        searches.process_dependency,
        searches.render_dependency,
        searches.assets_accessor_dependency,
        searches.reader_dependency,
        searches.backend_dependency,
    ],
    tags=["STAC Search"],
)
add_search_list_route(app, prefix="/searches", tags=["STAC Search"])
TITILER_CONFORMS_TO.update(searches.conforms_to)


@app.get("/searches/builder", response_class=HTMLResponse, tags=["STAC Search"])
async def virtual_mosaic_builder(request: Request):
    """Mosaic Builder Viewer."""
    base_url = str(request.base_url)
    return templates.TemplateResponse(
        name="mosaic-builder.html",
        context={
            "request": request,
            "register_endpoint": str(
                app.url_path_for("register_search").make_absolute_url(base_url=base_url)
            ),
            "collections_endpoint": str(
                app.url_path_for("list_collection").make_absolute_url(base_url=base_url)
            ),
        },
        media_type="text/html",
    )


###############################################################################
# STAC COLLECTION Endpoints
collection = MosaicTilerFactory(
    path_dependency=CollectionIdParams,
    router_prefix="/collections/{collection_id}",
    add_statistics=True,
    add_viewer=True,
    add_part=True,
    extensions=[
        searchInfoExtension(),
    ],
    templates=templates,
)
app.include_router(
    collection.router, tags=["STAC Collection"], prefix="/collections/{collection_id}"
)
TITILER_CONFORMS_TO.update(collection.conforms_to)

###############################################################################
# STAC Item Endpoints
stac = MultiBaseTilerFactory(
    reader=PgSTACReader,
    path_dependency=ItemIdParams,
    router_prefix="/collections/{collection_id}/items/{item_id}",
    add_viewer=True,
    templates=templates,
)


@stac.router.get("/viewer", response_class=HTMLResponse)
def viewer(request: Request, item: pystac.Item = Depends(stac.path_dependency)):
    """STAC Viewer

    Simplified version of https://github.com/developmentseed/titiler/blob/main/src/titiler/extensions/titiler/extensions/templates/stac_viewer.html
    """
    return templates.TemplateResponse(
        name="stac-viewer.html",
        context={
            "request": request,
            "endpoint": request.url.path.replace("/viewer", ""),
        },
        media_type="text/html",
    )


app.include_router(
    stac.router,
    tags=["STAC Item"],
    prefix="/collections/{collection_id}/items/{item_id}",
)
TITILER_CONFORMS_TO.update(stac.conforms_to)


###############################################################################
# STAC Assets Endpoints
asset = TilerFactory(
    path_dependency=AssetIdParams,
    router_prefix="/collections/{collection_id}/items/{item_id}/assets/{asset_id}",
    add_viewer=True,
    templates=templates,
)
app.include_router(
    asset.router,
    tags=["STAC Asset"],
    prefix="/collections/{collection_id}/items/{item_id}/assets/{asset_id}",
)
TITILER_CONFORMS_TO.update(asset.conforms_to)


###############################################################################
# External Dataset Endpoints
external_cog = TilerFactory(
    router_prefix="/external",
    extensions=[
        cogViewerExtension(),
    ],
    templates=templates,
)
app.include_router(
    external_cog.router,
    tags=["External Dataset"],
    prefix="/external",
)
TITILER_CONFORMS_TO.update(external_cog.conforms_to)

###############################################################################
# Tiling Schemes Endpoints
tms = TMSFactory(templates=templates)
app.include_router(tms.router, tags=["Tiling Schemes"])
TITILER_CONFORMS_TO.update(tms.conforms_to)

###############################################################################
# Algorithms Endpoints
algorithms = AlgorithmFactory(templates=templates)
app.include_router(algorithms.router, tags=["Algorithms"])
TITILER_CONFORMS_TO.update(algorithms.conforms_to)

###############################################################################
# Colormaps endpoints
cmaps = ColorMapFactory(templates=templates)
app.include_router(cmaps.router, tags=["ColorMaps"])
TITILER_CONFORMS_TO.update(cmaps.conforms_to)


###############################################################################
# Health Check Endpoint
@app.get("/healthz", description="Health Check", tags=["Health Check"])
def ping(
    timeout: int = Query(
        1, description="Timeout getting SQL connection from the pool."
    ),
) -> Dict:
    """Health check."""
    try:
        with app.state.dbpool.connection(timeout) as conn:
            conn.execute("SELECT 1")
            db_online = True
    except (OperationalError, PoolTimeout):
        db_online = False

    return {
        "database_online": db_online,
        "versions": {
            "titiler": titiler_version,
            "titiler.pgstac": titiler_pgstac_version,
            "rasterio": rasterio.__version__,
            "gdal": rasterio.__gdal_version__,
            "proj": rasterio.__proj_version__,
            "geos": rasterio.__geos_version__,
        },
    }


###############################################################################
# Landing page Endpoint
@app.get(
    "/",
    response_model=Landing,
    response_model_exclude_none=True,
    responses={
        200: {
            "content": {
                "text/html": {},
                "application/json": {},
            }
        },
    },
    tags=["OGC Common"],
)
def landing(
    request: Request,
    f: Annotated[
        Optional[Literal["html", "json"]],
        Query(
            description="Response MediaType. Defaults to endpoint's default or value defined in `accept` header."
        ),
    ] = None,
):
    """TiTiler landing page."""
    data = {
        "title": settings.name or "eoAPI-Raster",
        "links": [
            {
                "title": "Landing page",
                "href": str(request.url_for("landing")),
                "type": "text/html",
                "rel": "self",
            },
            {
                "title": "the API definition (JSON)",
                "href": str(request.url_for("openapi")),
                "type": "application/vnd.oai.openapi+json;version=3.0",
                "rel": "service-desc",
            },
            {
                "title": "the API documentation",
                "href": str(request.url_for("swagger_ui_html")),
                "type": "text/html",
                "rel": "service-doc",
            },
            {
                "title": "Conformance Declaration",
                "href": str(request.url_for("conformance")),
                "type": "text/html",
                "rel": "http://www.opengis.net/def/rel/ogc/1.0/conformance",
            },
            {
                "title": "eoAPI Virtual Mosaic list (JSON)",
                "href": str(app.url_path_for("list_searches")),
                "type": "application/json",
                "rel": "data",
            },
            {
                "title": "eoAPI Virtual Mosaic (Search) builder",
                "href": str(app.url_path_for("virtual_mosaic_builder")),
                "type": "text/html",
                "rel": "data",
            },
            {
                "title": "eoAPI Virtual Mosaic (Search) viewer (template URL)",
                "href": str(
                    app.url_path_for(
                        "map_viewer",
                        search_id="{search_id}",
                        tileMatrixSetId="{tileMatrixSetId}",
                    )
                ),
                "type": "text/html",
                "rel": "data",
                "templated": True,
            },
            {
                "title": "eoAPI Collection viewer (template URL)",
                "href": str(
                    app.url_path_for(
                        "map_viewer",
                        collection_id="{collection_id}",
                        tileMatrixSetId="{tileMatrixSetId}",
                    )
                ),
                "type": "text/html",
                "rel": "data",
                "templated": True,
            },
            {
                "title": "eoAPI Item viewer (template URL)",
                "href": str(
                    app.url_path_for(
                        "map_viewer",
                        collection_id="{collection_id}",
                        item_id="{item_id}",
                        tileMatrixSetId="{tileMatrixSetId}",
                    )
                ),
                "type": "text/html",
                "rel": "data",
                "templated": True,
            },
            {
                "title": "List of Available TileMatrixSets",
                "href": str(request.url_for("tilematrixsets")),
                "type": "application/json",
                "rel": "http://www.opengis.net/def/rel/ogc/1.0/tiling-schemes",
            },
            {
                "title": "List of Available Algorithms",
                "href": str(request.url_for("available_algorithms")),
                "type": "application/json",
                "rel": "data",
            },
            {
                "title": "List of Available ColorMaps",
                "href": str(request.url_for("available_colormaps")),
                "type": "application/json",
                "rel": "data",
            },
            {
                "title": "TiTiler-PgSTAC Documentation (external link)",
                "href": "https://stac-utils.github.io/titiler-pgstac/",
                "type": "text/html",
                "rel": "doc",
            },
            {
                "title": "TiTiler-PgSTAC source code (external link)",
                "href": "https://github.com/stac-utils/titiler-pgstac",
                "type": "text/html",
                "rel": "doc",
            },
        ],
    }

    if f:
        output_type = MediaType[f]
    else:
        accepted_media = [MediaType.html, MediaType.json]
        output_type = (
            accept_media_type(request.headers.get("accept", ""), accepted_media)
            or MediaType.json
        )

    if output_type == MediaType.html:
        return create_html_response(
            request,
            data,
            "landing",
            title="eoAPI-raster",
            templates=templates,
        )

    return data


@app.get(
    "/conformance",
    response_model=Conformance,
    response_model_exclude_none=True,
    responses={
        200: {
            "content": {
                "text/html": {},
                "application/json": {},
            }
        },
    },
    tags=["OGC Common"],
)
def conformance(
    request: Request,
    f: Annotated[
        Optional[Literal["html", "json"]],
        Query(
            description="Response MediaType. Defaults to endpoint's default or value defined in `accept` header."
        ),
    ] = None,
):
    """Conformance classes.

    Called with `GET /conformance`.

    Returns:
        Conformance classes which the server conforms to.

    """
    data = {"conformsTo": sorted(TITILER_CONFORMS_TO)}

    if f:
        output_type = MediaType[f]
    else:
        accepted_media = [MediaType.html, MediaType.json]
        output_type = (
            accept_media_type(request.headers.get("accept", ""), accepted_media)
            or MediaType.json
        )

    if output_type == MediaType.html:
        return create_html_response(
            request,
            data,
            "conformance",
            title="Conformance",
            templates=templates,
        )

    return data


# Add dependencies to routes
if auth_settings.openid_configuration_url:
    oidc_auth = OpenIdConnectAuth.from_settings(auth_settings)

    restricted_prefixes = ["/collections", "/searches"]
    for route in app.routes:
        if any(
            route.path.startswith(f"{app.root_path}{prefix}")
            for prefix in restricted_prefixes
        ):
            oidc_auth.apply_auth_dependencies(route, required_token_scopes=[])
