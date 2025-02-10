"""eoapi-devseed: Custom pgstac client."""

import re
from typing import Any, Dict, List, Literal, Optional, Type, get_args
from urllib.parse import urljoin

import attr
import jinja2
from fastapi import Request
from stac_fastapi.pgstac.core import CoreCrudClient
from stac_fastapi.pgstac.extensions.filter import FiltersClient as PgSTACFiltersClient
from stac_fastapi.pgstac.types.search import PgstacSearch
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
from stac_pydantic.shared import MimeTypes
from starlette.templating import Jinja2Templates, _TemplateResponse

ResponseType = Literal["json", "html"]
GeoResponseType = Literal["geojson", "html"]
QueryablesResponseType = Literal["jsonschema", "html"]


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
            return create_html_response(
                request,
                collections,
                template_name="collections",
                title="Collections list",
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
        *args,
        f: Optional[str] = None,
        **kwargs,
    ) -> ItemCollection:
        items = await super().item_collection(collection_id, request, *args, **kwargs)

        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(GeoResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        if output_type == MimeTypes.html:
            items["id"] = collection_id
            return create_html_response(
                request,
                items,
                template_name="items",
                title=f"{collection_id} items",
            )

        return items

    async def get_item(
        self,
        item_id: str,
        collection_id: str,
        request: Request,
        *args,
        f: Optional[str] = None,
        **kwargs,
    ) -> Item:
        item = await super().get_item(item_id, collection_id, request, *args, **kwargs)

        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(GeoResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        if output_type == MimeTypes.html:
            return create_html_response(
                request,
                item,
                template_name="item",
                title=f"{collection_id}/{item_id} item",
            )

        return item

    async def get_search(
        self,
        request: Request,
        *args,
        f: Optional[str] = None,
        **kwargs,
    ) -> ItemCollection:
        items = await super().get_search(request, *args, **kwargs)

        output_type: Optional[MimeTypes]
        if f:
            output_type = MimeTypes[f]
        else:
            accepted_media = [MimeTypes[v] for v in get_args(GeoResponseType)]
            output_type = accept_media_type(
                request.headers.get("accept", ""), accepted_media
            )

        if output_type == MimeTypes.html:
            return create_html_response(
                request,
                items,
                template_name="search",
            )

        return items
