"""eoapi-devseed: Custom pgstac client."""

import csv
import math
import re
from typing import (
    Any,
    Dict,
    Generator,
    Iterable,
    List,
    Literal,
    Optional,
    Type,
    get_args,
)
from urllib.parse import unquote_plus, urljoin

import attr
import jinja2
import orjson
from fastapi import Request
from geojson_pydantic.geometries import parse_geometry_obj
from stac_fastapi.api.models import JSONResponse
from stac_fastapi.pgstac.core import CoreCrudClient
from stac_fastapi.pgstac.extensions.filter import FiltersClient as PgSTACFiltersClient
from stac_fastapi.pgstac.models.links import ItemCollectionLinks
from stac_fastapi.pgstac.types.search import PgstacSearch
from stac_fastapi.types.errors import NotFoundError
from stac_fastapi.types.requests import get_base_url
from stac_fastapi.types.stac import (
    Collection,
    Collections,
    Conformance,
    Item,
    ItemCollection,
    LandingPage,
)
from stac_pydantic.links import Relations
from stac_pydantic.shared import BBox, MimeTypes
from starlette.responses import StreamingResponse
from starlette.templating import Jinja2Templates, _TemplateResponse

ResponseType = Literal["json", "html"]
GeoResponseType = Literal["geojson", "html"]
QueryablesResponseType = Literal["jsonschema", "html"]
GeoMultiResponseType = Literal["geojson", "html", "geojsonseq", "csv"]
PostMultiResponseType = Literal["geojson", "geojsonseq", "csv"]


jinja2_env = jinja2.Environment(
    loader=jinja2.ChoiceLoader([jinja2.PackageLoader(__package__, "templates")])
)
DEFAULT_TEMPLATES = Jinja2Templates(env=jinja2_env)


def accept_media_type(accept: str, mediatypes: List[MimeTypes]) -> Optional[MimeTypes]:
    """Return MediaType based on accept header and available mediatype.

    Links:
    - https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html
    - https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept

    """
    accept_values = {}
    for m in accept.replace(" ", "").split(","):
        values = m.split(";")
        if len(values) == 1:
            name = values[0]
            quality = 1.0
        else:
            name = values[0]
            groups = dict([param.split("=") for param in values[1:]])  # type: ignore
            try:
                q = groups.get("q")
                quality = float(q) if q else 1.0
            except ValueError:
                quality = 0

        # if quality is 0 we ignore encoding
        if quality:
            accept_values[name] = quality

    # Create Preference matrix
    media_preference = {
        v: [n for (n, q) in accept_values.items() if q == v]
        for v in sorted(set(accept_values.values()), reverse=True)
    }

    # Loop through available compression and encoding preference
    for _, pref in media_preference.items():
        for media in mediatypes:
            if media.value in pref:
                return media

    # If no specified encoding is supported but "*" is accepted,
    # take one of the available compressions.
    if "*" in accept_values and mediatypes:
        return mediatypes[0]

    return None


def create_html_response(
    request: Request,
    data: Any,
    template_name: str,
    title: Optional[str] = None,
    router_prefix: Optional[str] = None,
    **kwargs: Any,
) -> _TemplateResponse:
    """Create Template response."""

    router_prefix = request.app.state.router_prefix

    urlpath = request.url.path
    if root_path := request.app.root_path:
        urlpath = re.sub(r"^" + root_path, "", urlpath)

    if router_prefix:
        urlpath = re.sub(r"^" + router_prefix, "", urlpath)

    crumbs = []
    baseurl = str(request.base_url).rstrip("/")

    if router_prefix:
        baseurl += router_prefix

    crumbpath = str(baseurl)
    if urlpath == "/":
        urlpath = ""

    for crumb in urlpath.split("/"):
        crumbpath = crumbpath.rstrip("/")
        part = crumb
        if part is None or part == "":
            part = "Home"
        crumbpath += f"/{crumb}"
        crumbs.append({"url": crumbpath.rstrip("/"), "part": part.capitalize()})

    return DEFAULT_TEMPLATES.TemplateResponse(
        request,
        name=f"{template_name}.html",
        context={
            "response": data,
            "template": {
                "api_root": baseurl,
                "params": request.query_params,
                "title": title or template_name,
            },
            "crumbs": crumbs,
            "url": baseurl + urlpath,
            "params": str(request.url.query),
            **kwargs,
        },
    )


def _create_csv_rows(data: Iterable[Dict]) -> Generator[str, None, None]:
    """Creates an iterator that returns lines of csv from an iterable of dicts."""

    class DummyWriter:
        """Dummy writer that implements write for use with csv.writer."""

        def write(self, line: str):
            """Return line."""
            return line

    # Get the first row and construct the column names
    row = next(data)  # type: ignore
    fieldnames = row.keys()
    writer = csv.DictWriter(DummyWriter(), fieldnames=fieldnames)

    # Write header
    yield writer.writerow(dict(zip(fieldnames, fieldnames)))

    # Write first row
    yield writer.writerow(row)

    # Write all remaining rows
    for row in data:
        yield writer.writerow(row)


def items_to_csv_rows(items: Iterable[Dict]) -> Generator[str, None, None]:
    """Creates an iterator that returns lines of csv from an iterable of dicts."""
    if any(f.get("geometry", None) is not None for f in items):
        rows = (
            {
                "itemId": f.get("id"),
                "collectionId": f.get("collection"),
                **f.get("properties", {}),
                "geometry": parse_geometry_obj(f["geometry"]).wkt,
            }
            for f in items
        )
    else:
        rows = (
            {
                "itemId": f.get("id"),
                "collectionId": f.get("collection"),
                **f.get("properties", {}),
            }
            for f in items
        )

    return _create_csv_rows(rows)


@attr.s
class FiltersClient(PgSTACFiltersClient):
    async def get_queryables(
        self,
        request: Request,
        collection_id: Optional[str] = None,
        *args,
        f: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Get the queryables available for the given collection_id."""

        queryables = await super().get_queryables(
            request, collection_id, *args, **kwargs
        )

        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(QueryablesResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        if output_type == MimeTypes.html:
            return create_html_response(
                request,
                queryables,
                template_name="queryables",
                title=f"{collection_id} queryables",
            )

        return queryables


@attr.s
class PgSTACClient(CoreCrudClient):
    pgstac_search_model: Type[PgstacSearch] = attr.ib(default=PgstacSearch)

    async def landing_page(
        self,
        request: Request,
        f: Optional[str] = None,
        **kwargs,
    ) -> LandingPage:
        """Landing page.

        Called with `GET /`.

        Returns:
            API landing page, serving as an entry point to the API.

        """
        base_url = get_base_url(request)

        landing_page = self._landing_page(
            base_url=base_url,
            conformance_classes=self.conformance_classes(),
            extension_schemas=[],
        )

        # Add Queryables link
        if self.extension_is_enabled("FilterExtension") or self.extension_is_enabled(
            "SearchFilterExtension"
        ):
            landing_page["links"].append(
                {
                    "rel": Relations.queryables.value,
                    "type": MimeTypes.jsonschema.value,
                    "title": "Queryables",
                    "href": urljoin(base_url, "queryables"),
                }
            )

        # Add Aggregation links
        if self.extension_is_enabled("AggregationExtension"):
            landing_page["links"].extend(
                [
                    {
                        "rel": "aggregate",
                        "type": "application/json",
                        "title": "Aggregate",
                        "href": urljoin(base_url, "aggregate"),
                    },
                    {
                        "rel": "aggregations",
                        "type": "application/json",
                        "title": "Aggregations",
                        "href": urljoin(base_url, "aggregations"),
                    },
                ]
            )

        # Add OpenAPI URL
        landing_page["links"].append(
            {
                "rel": Relations.service_desc.value,
                "type": MimeTypes.openapi.value,
                "title": "OpenAPI service description",
                "href": str(request.url_for("openapi")),
            }
        )

        # Add human readable service-doc
        landing_page["links"].append(
            {
                "rel": Relations.service_doc.value,
                "type": MimeTypes.html.value,
                "title": "OpenAPI service documentation",
                "href": str(request.url_for("swagger_ui_html")),
            }
        )

        landing = LandingPage(**landing_page)

        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(ResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        if output_type == MimeTypes.html:
            return create_html_response(
                request,
                landing,
                template_name="landing",
                title=landing["title"],
            )

        return landing

    async def conformance(
        self,
        request: Request,
        f: Optional[str] = None,
        **kwargs,
    ) -> Conformance:
        """Conformance classes.

        Called with `GET /conformance`.

        Returns:
            Conformance classes which the server conforms to.
        """
        conforms_to = Conformance(conformsTo=self.conformance_classes())

        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(ResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        if output_type == MimeTypes.html:
            return create_html_response(
                request,
                conforms_to,
                template_name="conformance",
            )

        return conforms_to

    async def all_collections(
        self,
        request: Request,
        *args,
        f: Optional[str] = None,
        **kwargs,
    ) -> Collections:
        collections = await super().all_collections(request, *args, **kwargs)

        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(ResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        if output_type == MimeTypes.html:
            offset = int(request.query_params.get("offset") or 0)
            limit = int(request.query_params.get("limit") or 10)

            current_page = 1
            if limit > 0:
                current_page = math.ceil((offset + limit) / limit)

            return create_html_response(
                request,
                collections,
                template_name="collections",
                title="Collections list",
                current_page=current_page,
                limit=limit,
                offset=offset,
            )

        return collections

    async def get_collection(
        self,
        collection_id: str,
        request: Request,
        *args,
        f: Optional[str] = None,
        **kwargs,
    ) -> Collection:
        collection = await super().get_collection(
            collection_id, request, *args, **kwargs
        )

        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(ResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        if output_type == MimeTypes.html:
            return create_html_response(
                request,
                collection,
                template_name="collection",
                title=f"{collection_id} collection",
            )

        return collection

    async def item_collection(
        self,
        collection_id: str,
        request: Request,
        bbox: Optional[BBox] = None,
        datetime: Optional[str] = None,
        limit: Optional[int] = None,
        # Extensions
        query: Optional[str] = None,
        fields: Optional[List[str]] = None,
        sortby: Optional[str] = None,
        filter_expr: Optional[str] = None,
        filter_lang: Optional[str] = None,
        token: Optional[str] = None,
        f: Optional[str] = None,
        **kwargs,
    ) -> ItemCollection:
        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(GeoMultiResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        # Check if collection exist
        await self.get_collection(collection_id, request=request)

        base_args = {
            "collections": [collection_id],
            "bbox": bbox,
            "datetime": datetime,
            "limit": limit,
            "token": token,
            "query": orjson.loads(unquote_plus(query)) if query else query,
        }
        clean = self._clean_search_args(
            base_args=base_args,
            filter_query=filter_expr,
            filter_lang=filter_lang,
            fields=fields,
            sortby=sortby,
        )

        search_request = self.pgstac_search_model(**clean)
        item_collection = await self._search_base(search_request, request=request)
        item_collection["links"] = await ItemCollectionLinks(
            collection_id=collection_id, request=request
        ).get_links(extra_links=item_collection["links"])

        # Additional Headers for StreamingResponse
        additional_headers = {}
        links = item_collection.get("links", [])
        next_link = next(filter(lambda link: link["rel"] == "next", links), None)
        prev_link = next(
            filter(lambda link: link["rel"] in ["prev", "previous"], links), None
        )
        if next_link or prev_link:
            additional_headers["Link"] = ",".join(
                [
                    f'<{link["href"]}>; rel="{link["rel"]}"'
                    for link in [next_link, prev_link]
                    if link
                ]
            )

        if output_type == MimeTypes.html:
            item_collection["id"] = collection_id
            return create_html_response(
                request,
                item_collection,
                template_name="items",
                title=f"{collection_id} items",
                limit=limit
            )

        elif output_type == MimeTypes.csv:
            return StreamingResponse(
                items_to_csv_rows(item_collection["features"]),
                media_type=MimeTypes.csv,
                headers={
                    "Content-Disposition": "attachment;filename=items.csv",
                    **additional_headers,
                },
            )

        elif output_type == MimeTypes.geojsonseq:
            return StreamingResponse(
                (orjson.dumps(f) + b"\n" for f in item_collection["features"]),
                media_type=MimeTypes.geojsonseq,
                headers={
                    "Content-Disposition": "attachment;filename=items.geojson",
                    **additional_headers,
                },
            )

        # If we have the `fields` extension enabled
        # we need to avoid Pydantic validation because the
        # Items might not be a valid STAC Item objects
        if fields := getattr(search_request, "fields", None):
            if fields.include or fields.exclude:
                return JSONResponse(item_collection)  # type: ignore

        return ItemCollection(**item_collection)

    async def get_item(
        self,
        item_id: str,
        collection_id: str,
        request: Request,
        f: Optional[str] = None,
        **kwargs,
    ) -> Item:
        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(GeoResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        # Check if collection exist
        await self.get_collection(collection_id, request=request)

        search_request = self.pgstac_search_model(
            ids=[item_id], collections=[collection_id], limit=1
        )
        item_collection = await self._search_base(search_request, request=request)
        if not item_collection["features"]:
            raise NotFoundError(
                f"Item {item_id} in Collection {collection_id} does not exist."
            )

        if output_type == MimeTypes.html:
            return create_html_response(
                request,
                item_collection["features"][0],
                template_name="item",
                title=f"{collection_id}/{item_id} item",
            )

        return Item(**item_collection["features"][0])

    async def get_search(
        self,
        request: Request,
        collections: Optional[List[str]] = None,
        ids: Optional[List[str]] = None,
        bbox: Optional[BBox] = None,
        intersects: Optional[str] = None,
        datetime: Optional[str] = None,
        limit: Optional[int] = None,
        # Extensions
        query: Optional[str] = None,
        fields: Optional[List[str]] = None,
        sortby: Optional[str] = None,
        filter_expr: Optional[str] = None,
        filter_lang: Optional[str] = None,
        token: Optional[str] = None,
        f: Optional[str] = None,
        **kwargs,
    ) -> ItemCollection:
        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(GeoMultiResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        # Parse request parameters
        base_args = {
            "collections": collections,
            "ids": ids,
            "bbox": bbox,
            "limit": limit,
            "token": token,
            "query": orjson.loads(unquote_plus(query)) if query else query,
        }

        clean = self._clean_search_args(
            base_args=base_args,
            intersects=intersects,
            datetime=datetime,
            fields=fields,
            sortby=sortby,
            filter_query=filter_expr,
            filter_lang=filter_lang,
        )

        search_request = self.pgstac_search_model(**clean)
        item_collection = await self._search_base(search_request, request=request)

        # Additional Headers for StreamingResponse
        additional_headers = {}
        links = item_collection.get("links", [])
        next_link = next(filter(lambda link: link["rel"] == "next", links), None)
        prev_link = next(
            filter(lambda link: link["rel"] in ["prev", "previous"], links), None
        )
        if next_link or prev_link:
            additional_headers["Link"] = ",".join(
                [
                    f'<{link["href"]}>; rel="{link["rel"]}"'
                    for link in [next_link, prev_link]
                    if link
                ]
            )

        if output_type == MimeTypes.html:
            return create_html_response(
                request,
                item_collection,
                template_name="search",
            )

        elif output_type == MimeTypes.csv:
            return StreamingResponse(
                items_to_csv_rows(item_collection["features"]),
                media_type=MimeTypes.csv,
                headers={
                    "Content-Disposition": "attachment;filename=items.csv",
                    **additional_headers,
                },
            )

        elif output_type == MimeTypes.geojsonseq:
            return StreamingResponse(
                (orjson.dumps(f) + b"\n" for f in item_collection["features"]),
                media_type=MimeTypes.geojsonseq,
                headers={
                    "Content-Disposition": "attachment;filename=items.geojson",
                    **additional_headers,
                },
            )

        if fields := getattr(search_request, "fields", None):
            if fields.include or fields.exclude:
                return JSONResponse(item_collection)  # type: ignore

        return ItemCollection(**item_collection)

    async def post_search(
        self,
        search_request: PgstacSearch,
        request: Request,
        **kwargs,
    ) -> ItemCollection:
        accepted_media = [MimeTypes[v] for v in get_args(PostMultiResponseType)]
        output_type = accept_media_type(
            request.headers.get("accept", ""), accepted_media
        )

        item_collection = await self._search_base(search_request, request=request)

        # Additional Headers for StreamingResponse
        additional_headers = {}
        links = item_collection.get("links", [])
        next_link = next(filter(lambda link: link["rel"] == "next", links), None)
        prev_link = next(
            filter(lambda link: link["rel"] in ["prev", "previous"], links), None
        )
        if next_link or prev_link:
            additional_headers["Pagination-Token"] = ",".join(
                [
                    f'<{link["body"]["token"]}>; rel="{link["rel"]}"'
                    for link in [next_link, prev_link]
                    if link
                ]
            )

        if output_type == MimeTypes.csv:
            return StreamingResponse(
                items_to_csv_rows(item_collection["features"]),
                media_type=MimeTypes.csv,
                headers={
                    "Content-Disposition": "attachment;filename=items.csv",
                    **additional_headers,
                },
            )

        elif output_type == MimeTypes.geojsonseq:
            return StreamingResponse(
                (orjson.dumps(f) + b"\n" for f in item_collection["features"]),
                media_type=MimeTypes.geojsonseq,
                headers={
                    "Content-Disposition": "attachment;filename=items.geojson",
                    **additional_headers,
                },
            )

        if fields := getattr(search_request, "fields", None):
            if fields.include or fields.exclude:
                return JSONResponse(item_collection)  # type: ignore

        return ItemCollection(**item_collection)
