"""TiTiler extension."""

from typing import Annotated, Literal, Optional
from urllib.parse import urlencode

import attr
from fastapi import APIRouter, FastAPI, HTTPException, Path, Query
from fastapi.responses import RedirectResponse
from stac_fastapi.api.models import CollectionUri
from stac_fastapi.api.routes import create_async_endpoint
from stac_fastapi.extensions import core
from stac_fastapi.types.extension import ApiExtension
from stac_fastapi.types.search import APIRequest
from stac_pydantic.shared import MimeTypes
from starlette.requests import Request


@attr.s(kw_only=True)
class TiTilerExtension(ApiExtension):
    """TiTiler extension."""

    titiler_endpoint: str = attr.ib()
    router: APIRouter = attr.ib(factory=APIRouter)

    def register(self, app: FastAPI) -> None:
        """Register the extension with a FastAPI application.
        Args:
            app: target FastAPI application.
        Returns:
            None

        """
        self.router.prefix = app.state.router_prefix

        @self.router.get(
            "/collections/{collection_id}/items/{item_id}/tilejson.json",
        )
        async def tilejson(
            request: Request,
            collection_id: str = Path(description="Collection ID"),
            item_id: str = Path(description="Item ID"),
            tile_format: Optional[str] = Query(
                None, description="Output image type. Default is auto."
            ),
            tile_scale: int = Query(
                1, gt=0, lt=4, description="Tile size scale. 1=256x256, 2=512x512..."
            ),
            minzoom: Optional[int] = Query(
                None, description="Overwrite default minzoom."
            ),
            maxzoom: Optional[int] = Query(
                None, description="Overwrite default maxzoom."
            ),
            assets: Optional[str] = Query(  # noqa
                None,
                description="comma (',') delimited asset names.",
            ),
            expression: Optional[str] = Query(  # noqa
                None,
                description="rio-tiler's band math expression between assets (e.g asset1/asset2)",
            ),
            bidx: Optional[str] = Query(  # noqa
                None,
                description="comma (',') delimited band indexes to apply to each asset",
            ),
        ):
            """Get items and redirect to stac tiler."""
            if not assets and not expression:
                raise HTTPException(
                    status_code=500,
                    detail="assets must be defined either via expression or assets options.",
                )

            qs_key_to_remove = [
                "tile_format",
                "tile_scale",
                "minzoom",
                "maxzoom",
            ]
            qs = [
                (key, value)
                for (key, value) in request.query_params._list
                if key.lower() not in qs_key_to_remove
            ]
            return RedirectResponse(
                f"{self.titiler_endpoint}/collections/{collection_id}/items/{item_id}/tilejson.json?{urlencode(qs)}"
            )

        @self.router.get(
            "/collections/{collection_id}/items/{item_id}/viewer",
            responses={
                200: {
                    "description": "Redirect to TiTiler STAC viewer.",
                    "content": {"text/html": {}},
                }
            },
        )
        async def stac_viewer(
            request: Request,
            collection_id: str = Path(description="Collection ID"),
            item_id: str = Path(description="Item ID"),
        ):
            """Get items and redirect to stac tiler."""
            qs = [(key, value) for (key, value) in request.query_params._list]
            url = f"{self.titiler_endpoint}/collections/{collection_id}/items/{item_id}/viewer"
            if qs:
                url += f"?{urlencode(qs)}"

            return RedirectResponse(url)

        app.include_router(self.router, tags=["TiTiler Extension"])


@attr.s
class HTMLorJSONGetRequest(APIRequest):
    """HTML or JSON output."""

    f: Annotated[
        Optional[Literal["json", "html"]],
        Query(description="Response MediaType."),
    ] = attr.ib(default=None)


@attr.s
class HTMLorGeoGetRequest(APIRequest):
    """HTML or GeoJSON output."""

    f: Annotated[
        Optional[Literal["geojson", "html"]],
        Query(description="Response MediaType."),
    ] = attr.ib(default=None)


@attr.s
class HTMLorGeoGetRequestMulti(APIRequest):
    """HTML, GeoJSON, GeoJSONSeq or CSV output."""

    f: Annotated[
        Optional[Literal["geojson", "html", "csv", "geojsonseq", "parquet"]],
        Query(description="Response MediaType."),
    ] = attr.ib(default=None)


@attr.s(kw_only=True)
class HTMLorJSONOutputExtension(ApiExtension):
    """TiTiler extension."""

    GET = HTMLorJSONGetRequest
    POST = None

    def register(self, app: FastAPI) -> None:
        pass


@attr.s(kw_only=True)
class HTMLorGeoOutputExtension(ApiExtension):
    """TiTiler extension."""

    GET = HTMLorGeoGetRequest
    POST = None

    def register(self, app: FastAPI) -> None:
        pass


@attr.s(kw_only=True)
class HTMLorGeoMultiOutputExtension(ApiExtension):
    """TiTiler extension."""

    GET = HTMLorGeoGetRequestMulti
    POST = None

    def register(self, app: FastAPI) -> None:
        pass


@attr.s(kw_only=True)
class HTMLorSchemaGetRequest(APIRequest):
    f: Annotated[
        Optional[Literal["jsonschema", "html"]],
        Query(description="Response MediaType."),
    ] = attr.ib(default=None)


@attr.s(kw_only=True)
class CollectionFilterGetRequestModel(CollectionUri, HTMLorSchemaGetRequest):
    pass


@attr.s
class SearchFilterExtension(core.SearchFilterExtension):
    """Item Search Filter Extension."""

    def register(self, app: FastAPI) -> None:
        """Register the extension with a FastAPI application.

        Args:
            app: target FastAPI application.

        Returns:
            None
        """
        self.router.prefix = app.state.router_prefix
        self.router.add_api_route(
            name="Queryables",
            path="/queryables",
            methods=["GET"],
            responses={
                200: {
                    "content": {
                        MimeTypes.jsonschema.value: {},
                        MimeTypes.html.value: {},
                    },
                },
            },
            response_class=self.response_class,
            endpoint=create_async_endpoint(
                self.client.get_queryables, HTMLorSchemaGetRequest
            ),
        )
        app.include_router(self.router, tags=["Filter Extension"])


@attr.s
class ItemCollectionFilterExtension(core.ItemCollectionFilterExtension):
    """Item Collection Filter Extension."""

    def register(self, app: FastAPI) -> None:
        """Register the extension with a FastAPI application.

        Args:
            app: target FastAPI application.

        Returns:
            None
        """
        self.router.prefix = app.state.router_prefix
        self.router.add_api_route(
            name="Collection Queryables",
            path="/collections/{collection_id}/queryables",
            methods=["GET"],
            responses={
                200: {
                    "content": {
                        MimeTypes.jsonschema.value: {},
                        MimeTypes.html.value: {},
                    },
                },
            },
            response_class=self.response_class,
            endpoint=create_async_endpoint(
                self.client.get_queryables, CollectionFilterGetRequestModel
            ),
        )
        app.include_router(self.router, tags=["Filter Extension"])
