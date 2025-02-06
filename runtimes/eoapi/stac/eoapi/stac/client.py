"""eoapi-devseed: Custom pgstac client."""

from typing import Type
from urllib.parse import urljoin

import attr
from fastapi import Request
from stac_fastapi.pgstac.core import CoreCrudClient
from stac_fastapi.pgstac.types.search import PgstacSearch
from stac_fastapi.types.requests import get_base_url
from stac_fastapi.types.stac import LandingPage
from stac_pydantic.links import Relations
from stac_pydantic.shared import MimeTypes


@attr.s
class PgSTACClient(CoreCrudClient):
    pgstac_search_model: Type[PgstacSearch] = attr.ib(default=PgstacSearch)

    async def landing_page(
        self,
        request: Request,
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

        return LandingPage(**landing_page)
