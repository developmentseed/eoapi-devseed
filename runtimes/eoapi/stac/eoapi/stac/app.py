"""eoapi.stac app."""

import logging
from contextlib import asynccontextmanager

import jinja2
from eoapi.auth_utils import OpenIdConnectAuth, OpenIdConnectSettings
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from stac_fastapi.api.app import StacApi
from stac_fastapi.api.models import (
    EmptyRequest,
    ItemCollectionUri,
    create_get_request_model,
    create_post_request_model,
    create_request_model,
)
from stac_fastapi.extensions.core import (
    CollectionSearchExtension,
    CollectionSearchFilterExtension,
    FieldsExtension,
    FreeTextExtension,
    ItemCollectionFilterExtension,
    OffsetPaginationExtension,
    SearchFilterExtension,
    SortExtension,
    TokenPaginationExtension,
    TransactionExtension,
)
from stac_fastapi.extensions.core.fields import FieldsConformanceClasses
from stac_fastapi.extensions.core.free_text import FreeTextConformanceClasses
from stac_fastapi.extensions.core.query import QueryConformanceClasses
from stac_fastapi.extensions.core.sort import SortConformanceClasses
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

from .config import ApiSettings
from .extension import TiTilerExtension
from .logs import init_logging

jinja2_env = jinja2.Environment(
    loader=jinja2.ChoiceLoader(
        [
            jinja2.PackageLoader(__package__, "templates"),
        ]
    )
)
templates = Jinja2Templates(env=jinja2_env)

api_settings = ApiSettings()
auth_settings = OpenIdConnectSettings()
settings = Settings(enable_response_models=True)

enabled_extensions = api_settings.extensions or []

# Logs
init_logging(debug=api_settings.debug)
logger = logging.getLogger(__name__)

# Extensions
# application extensions
application_extensions_map = {
    "transaction": TransactionExtension(
        client=TransactionsClient(),
        settings=settings,
        response_class=ORJSONResponse,
    ),
    "bulk_transactions": BulkTransactionExtension(client=BulkTransactionsClient()),
}
if "titiler" in enabled_extensions and api_settings.titiler_endpoint:
    application_extensions_map["titiler"] = TiTilerExtension(
        titiler_endpoint=api_settings.titiler_endpoint
    )

# search extensions
search_extensions_map = {
    "query": QueryExtension(),
    "sort": SortExtension(),
    "fields": FieldsExtension(),
    "filter": SearchFilterExtension(client=FiltersClient()),
    "pagination": TokenPaginationExtension(),
}

# collection_search extensions
cs_extensions_map = {
    "query": QueryExtension(conformance_classes=[QueryConformanceClasses.COLLECTIONS]),
    "sort": SortExtension(conformance_classes=[SortConformanceClasses.COLLECTIONS]),
    "fields": FieldsExtension(
        conformance_classes=[FieldsConformanceClasses.COLLECTIONS]
    ),
    "filter": CollectionSearchFilterExtension(client=FiltersClient()),
    "free_text": FreeTextExtension(
        conformance_classes=[FreeTextConformanceClasses.COLLECTIONS],
    ),
    "pagination": OffsetPaginationExtension(),
}

# item_collection extensions
itm_col_extensions_map = {
    "query": QueryExtension(
        conformance_classes=[QueryConformanceClasses.ITEMS],
    ),
    "sort": SortExtension(
        conformance_classes=[SortConformanceClasses.ITEMS],
    ),
    "fields": FieldsExtension(conformance_classes=[FieldsConformanceClasses.ITEMS]),
    "filter": ItemCollectionFilterExtension(client=FiltersClient()),
    "pagination": TokenPaginationExtension(),
}

application_extensions = [
    extension
    for key, extension in application_extensions_map.items()
    if key in enabled_extensions
]

# Request Models
# /search models
search_extensions = [
    extension
    for key, extension in search_extensions_map.items()
    if key in enabled_extensions
]
post_request_model = create_post_request_model(
    search_extensions, base_model=PgstacSearch
)
get_request_model = create_get_request_model(search_extensions)
application_extensions.extend(search_extensions)

# /collections/{collectionId}/items model
items_get_request_model = ItemCollectionUri
itm_col_extensions = [
    extension
    for key, extension in itm_col_extensions_map.items()
    if key in enabled_extensions
]
if itm_col_extensions:
    items_get_request_model = create_request_model(
        model_name="ItemCollectionUri",
        base_model=ItemCollectionUri,
        extensions=itm_col_extensions,
        request_type="GET",
    )
    application_extensions.extend(itm_col_extensions)

# /collections model
collections_get_request_model = EmptyRequest
if "collection_search" in enabled_extensions:
    cs_extensions = [
        extension
        for key, extension in cs_extensions_map.items()
        if key in enabled_extensions
    ]
    collection_search_extension = CollectionSearchExtension.from_extensions(
        cs_extensions
    )
    collections_get_request_model = collection_search_extension.GET
    application_extensions.append(collection_search_extension)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan."""
    await connect_to_db(app)
    yield
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
    extensions=application_extensions,
    client=CoreCrudClient(pgstac_search_model=post_request_model),
    items_get_request_model=items_get_request_model,
    search_get_request_model=get_request_model,
    search_post_request_model=post_request_model,
    collections_get_request_model=collections_get_request_model,
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
