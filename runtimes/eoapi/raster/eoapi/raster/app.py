"""eoAPI Raster application."""

import logging
import re
from contextlib import asynccontextmanager
from typing import Dict

import jinja2
import pystac
from fastapi import Depends, FastAPI, Query
from psycopg import OperationalError
from psycopg.rows import dict_row
from psycopg_pool import PoolTimeout
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from starlette_cramjam.middleware import CompressionMiddleware
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.core.factory import (
    AlgorithmFactory,
    ColorMapFactory,
    MultiBaseTilerFactory,
    TilerFactory,
    TMSFactory,
)
from titiler.core.middleware import CacheControlMiddleware
from titiler.extensions import cogViewerExtension
from titiler.mosaic.errors import MOSAIC_STATUS_CODES
from titiler.pgstac.db import close_db_connection, connect_to_db
from titiler.pgstac.dependencies import CollectionIdParams, ItemIdParams, SearchIdParams
from titiler.pgstac.extensions import searchInfoExtension
from titiler.pgstac.factory import (
    MosaicTilerFactory,
    add_search_list_route,
    add_search_register_route,
)
from titiler.pgstac.reader import PgSTACReader

from . import __version__ as eoapi_raster_version
from . import auth, config, logs

settings = config.ApiSettings()
auth_settings = auth.AuthSettings()


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


logger.debug("Loading jinja2 templates...")
jinja2_env = jinja2.Environment(
    loader=jinja2.ChoiceLoader(
        [
            jinja2.PackageLoader(__package__, "templates"),
        ]
    )
)
templates = Jinja2Templates(env=jinja2_env)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan."""
    logger.debug("Connecting to db...")
    await connect_to_db(app)
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
        searches.tile_dependency,
        searches.process_dependency,
        searches.rescale_dependency,
        searches.colormap_dependency,
        searches.render_dependency,
        searches.pgstac_dependency,
        searches.reader_dependency,
        searches.backend_dependency,
    ],
    tags=["STAC Search"],
)
add_search_list_route(app, prefix="/searches", tags=["STAC Search"])


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
)
app.include_router(
    collection.router, tags=["STAC Collection"], prefix="/collections/{collection_id}"
)


###############################################################################
# STAC Item Endpoints
stac = MultiBaseTilerFactory(
    reader=PgSTACReader,
    path_dependency=ItemIdParams,
    router_prefix="/collections/{collection_id}/items/{item_id}",
    add_viewer=True,
)
app.include_router(
    stac.router,
    tags=["STAC Item"],
    prefix="/collections/{collection_id}/items/{item_id}",
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


###############################################################################
# COG Endpoints
cog = TilerFactory(
    router_prefix="/cog",
    extensions=[
        cogViewerExtension(),
    ],
)

app.include_router(cog.router, prefix="/cog", tags=["Cloud Optimized GeoTIFF"])

###############################################################################
# Tiling Schemes Endpoints
tms = TMSFactory()
app.include_router(tms.router, tags=["Tiling Schemes"])

###############################################################################
# Algorithms Endpoints
algorithms = AlgorithmFactory()
app.include_router(algorithms.router, tags=["Algorithms"])

###############################################################################
# Colormaps endpoints
cmaps = ColorMapFactory()
app.include_router(
    cmaps.router,
    tags=["ColorMaps"],
)


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
            with conn.cursor() as cursor:
                cursor.execute("SELECT version from pgstac.migrations;")
                version = cursor.fetchone()
        return {"database_online": True, "pgstac_version": version}
    except (OperationalError, PoolTimeout):
        return {"database_online": False}


###############################################################################
# Landing page Endpoint
@app.get(
    "/",
    response_class=HTMLResponse,
    tags=["Landing"],
)
def landing(request: Request):
    """Get landing page."""
    data = {
        "title": settings.name or "eoAPI-raster",
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
                "title": "eoAPI Virtual Mosaic list (JSON)",
                "href": str(app.url_path_for("list_searches")),
                "type": "application/json",
                "rel": "data",
            },
            {
                "title": "eoAPI Virtual Mosaic builder",
                "href": str(app.url_path_for("virtual_mosaic_builder")),
                "type": "text/html",
                "rel": "data",
            },
            {
                "title": "eoAPI Virtual Mosaic viewer (template URL)",
                "href": str(app.url_path_for("map_viewer", search_id="{search_id}")),
                "type": "text/html",
                "rel": "data",
                "templated": True,
            },
            {
                "title": "eoAPI Collection viewer (template URL)",
                "href": str(
                    app.url_path_for("map_viewer", collection_id="{collection_id}")
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
                    )
                ),
                "type": "text/html",
                "rel": "data",
                "templated": True,
            },
        ],
    }

    urlpath = request.url.path
    if root_path := request.app.root_path:
        urlpath = re.sub(r"^" + root_path, "", urlpath)
    crumbs = []
    baseurl = str(request.base_url).rstrip("/")

    crumbpath = str(baseurl)
    for crumb in urlpath.split("/"):
        crumbpath = crumbpath.rstrip("/")
        part = crumb
        if part is None or part == "":
            part = "Home"
        crumbpath += f"/{crumb}"
        crumbs.append({"url": crumbpath.rstrip("/"), "part": part.capitalize()})

    return templates.TemplateResponse(
        request,
        name="landing.html",
        context={
            "request": request,
            "response": data,
            "template": {
                "api_root": baseurl,
                "params": request.query_params,
                "title": "TiTiler-PgSTAC",
            },
            "crumbs": crumbs,
            "url": str(request.url),
            "baseurl": baseurl,
            "urlpath": str(request.url.path),
            "urlparams": str(request.url.query),
        },
    )


# Add dependencies to routes
if auth_settings.openid_configuration_url and not auth_settings.public_reads:
    oidc_auth = auth.OidcAuth(
        # URL to the OpenID Connect discovery document (https://openid.net/specs/openid-connect-discovery-1_0.html)
        openid_configuration_url=auth_settings.openid_configuration_url,
        openid_configuration_internal_url=auth_settings.openid_configuration_internal_url,
        # Optionally validate the "aud" claim in the JWT
        allowed_jwt_audiences=auth_settings.allowed_jwt_audiences,
        # To render scopes form on Swagger UI's login pop-up, populate with mapping of scopes to descriptions
        oauth2_supported_scopes={},
    )

    restricted_prefixes = ["/searches", "/collections"]
    for route in app.routes:
        if not any(
            route.path.startswith(f"{app.root_path}{prefix}")
            for prefix in restricted_prefixes
        ):
            continue
        oidc_auth.apply_auth_dependencies(route, required_token_scopes=[])
