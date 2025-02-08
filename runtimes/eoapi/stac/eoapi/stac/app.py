"""eoapi.stac app."""

import logging
from contextlib import asynccontextmanager

import jinja2
from eoapi.auth_utils import OpenIdConnectAuth, OpenIdConnectSettings
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from stac_fastapi.api.models import (
    CollectionUri,
    ItemCollectionUri,
    ItemUri,
    create_get_request_model,
    create_post_request_model,
    create_request_model,
)
from stac_fastapi.extensions.core import (
    CollectionSearchExtension,
    CollectionSearchFilterExtension,
    FieldsExtension,
    FreeTextExtension,
    OffsetPaginationExtension,
    SortExtension,
    TokenPaginationExtension,
)
from stac_fastapi.extensions.core.fields import FieldsConformanceClasses
from stac_fastapi.extensions.core.free_text import FreeTextConformanceClasses
from stac_fastapi.extensions.core.query import QueryConformanceClasses
from stac_fastapi.extensions.core.sort import SortConformanceClasses
from stac_fastapi.pgstac.db import close_db_connection, connect_to_db
from stac_fastapi.pgstac.extensions import QueryExtension
from stac_fastapi.pgstac.types.search import PgstacSearch
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from starlette_cramjam.middleware import CompressionMiddleware

from . import __version__ as eoapi_devseed_version
from .api import StacApi
from .client import FiltersClient, PgSTACClient
from .config import Settings
from .extensions import (
    HTMLorGeoOutputExtension,
    HTMLorJSONOutputExtension,
    ItemCollectionFilterExtension,
    SearchFilterExtension,
    TiTilerExtension,
)
from .logs import init_logging

jinja2_env = jinja2.Environment(
    loader=jinja2.ChoiceLoader(
        [
            jinja2.PackageLoader(__package__, "templates"),
        ]
    )
)
templates = Jinja2Templates(env=jinja2_env)

settings = Settings()
auth_settings = OpenIdConnectSettings()


# Logs
init_logging(debug=settings.debug)
logger = logging.getLogger(__name__)

# Extensions
# application extensions
application_extensions = []

if settings.titiler_endpoint:
    application_extensions.append(
        TiTilerExtension(titiler_endpoint=settings.titiler_endpoint)
    )

# search extensions
search_extensions = [
    QueryExtension(),
    SortExtension(),
    FieldsExtension(),
    SearchFilterExtension(client=FiltersClient()),  # type: ignore
    TokenPaginationExtension(),
    HTMLorGeoOutputExtension(),
]

# collection_search extensions
cs_extensions = [
    QueryExtension(conformance_classes=[QueryConformanceClasses.COLLECTIONS]),
    SortExtension(conformance_classes=[SortConformanceClasses.COLLECTIONS]),
    FieldsExtension(conformance_classes=[FieldsConformanceClasses.COLLECTIONS]),
    CollectionSearchFilterExtension(client=FiltersClient()),
    FreeTextExtension(
        conformance_classes=[FreeTextConformanceClasses.COLLECTIONS],
    ),
    OffsetPaginationExtension(),
    HTMLorJSONOutputExtension(),
]

# item_collection extensions
itm_col_extensions = [
    QueryExtension(
        conformance_classes=[QueryConformanceClasses.ITEMS],
    ),
    SortExtension(
        conformance_classes=[SortConformanceClasses.ITEMS],
    ),
    FieldsExtension(conformance_classes=[FieldsConformanceClasses.ITEMS]),
    ItemCollectionFilterExtension(client=FiltersClient()),  # type: ignore
    TokenPaginationExtension(),
    HTMLorGeoOutputExtension(),
]

# Request Models
# /search models
search_post_model = create_post_request_model(
    search_extensions, base_model=PgstacSearch
)
search_get_model = create_get_request_model(search_extensions)
application_extensions.extend(search_extensions)

# /collections/{collectionId}/items model
items_get_model = create_request_model(
    model_name="ItemCollectionUri",
    base_model=ItemCollectionUri,
    extensions=itm_col_extensions,
    request_type="GET",
)
application_extensions.extend(itm_col_extensions)

# /collections model
collection_search_extension = CollectionSearchExtension.from_extensions(cs_extensions)
collections_get_model = collection_search_extension.GET
application_extensions.append(collection_search_extension)

# /collections/{collectionId} model
collection_get_model = create_request_model(
    model_name="CollectionUri",
    base_model=CollectionUri,
    extensions=[HTMLorJSONOutputExtension()],
    request_type="GET",
)

# /collections/{collectionId}/items/itemId model
item_get_model = create_request_model(
    model_name="ItemUri",
    base_model=ItemUri,
    extensions=[HTMLorGeoOutputExtension()],
    request_type="GET",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan."""
    await connect_to_db(app)
    yield
    await close_db_connection(app)


# Middlewares
middlewares = [Middleware(CompressionMiddleware)]
if settings.cors_origins:
    middlewares.append(
        Middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=settings.cors_methods,
            allow_headers=["*"],
        )
    )

api = StacApi(
    app=FastAPI(
        title=settings.stac_fastapi_title,
        description=settings.stac_fastapi_description,
        version=eoapi_devseed_version,
        lifespan=lifespan,
        openapi_url=settings.openapi_url,
        docs_url=settings.docs_url,
        redoc_url=None,
        swagger_ui_init_oauth={
            "clientId": auth_settings.client_id,
            "usePkceWithAuthorizationCodeGrant": auth_settings.use_pkce,
        },
    ),
    api_version=eoapi_devseed_version,
    settings=settings,
    extensions=application_extensions,
    client=PgSTACClient(  # type: ignore
        landing_page_id=settings.stac_fastapi_landing_id,
        title=settings.stac_fastapi_title,
        description=settings.stac_fastapi_description,
        pgstac_search_model=search_post_model,
    ),
    item_get_request_model=item_get_model,
    items_get_request_model=items_get_model,
    collection_get_request_model=collection_get_model,
    collections_get_request_model=collections_get_model,
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
    oidc_auth = OpenIdConnectAuth.from_settings(auth_settings)

    restricted_prefixes = ["/collections", "/search"]
    for route in app.routes:
        if any(
            route.path.startswith(f"{app.root_path}{prefix}")
            for prefix in restricted_prefixes
        ):
            oidc_auth.apply_auth_dependencies(route, required_token_scopes=[])
