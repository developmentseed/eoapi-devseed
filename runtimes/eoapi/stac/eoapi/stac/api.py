"""eoapi.stac.api: custom StacAPI class."""

from typing import Type

import attr
from stac_fastapi.api import app
from stac_fastapi.api.models import APIRequest, GeoJSONResponse
from stac_fastapi.api.routes import create_async_endpoint
from stac_pydantic import api
from stac_pydantic.api.collections import Collections
from stac_pydantic.shared import MimeTypes

from .extensions import HTMLorJSONGetRequest


@attr.s
class StacApi(app.StacApi):
    """Custom StacAPI."""

    landing_get_model: Type[APIRequest] = attr.ib(default=HTMLorJSONGetRequest)
    conformance_get_model: Type[APIRequest] = attr.ib(default=HTMLorJSONGetRequest)

    def register_landing_page(self):
        """Register landing page (GET /).

        Returns:
            None
        """
        self.router.add_api_route(
            name="Landing Page",
            path="/",
            response_model=(
                api.LandingPage if self.settings.enable_response_models else None
            ),
            responses={
                200: {
                    "content": {
                        MimeTypes.json.value: {},
                        MimeTypes.html.value: {},
                    },
                    "model": api.LandingPage,
                },
            },
            response_class=self.response_class,
            response_model_exclude_unset=False,
            response_model_exclude_none=True,
            methods=["GET"],
            endpoint=create_async_endpoint(
                self.client.landing_page, self.landing_get_model
            ),
        )

    def register_conformance_classes(self):
        """Register conformance classes (GET /conformance).

        Returns:
            None
        """
        self.router.add_api_route(
            name="Conformance Classes",
            path="/conformance",
            response_model=(
                api.Conformance if self.settings.enable_response_models else None
            ),
            responses={
                200: {
                    "content": {
                        MimeTypes.json.value: {},
                        MimeTypes.html.value: {},
                    },
                    "model": api.Conformance,
                },
            },
            response_class=self.response_class,
            response_model_exclude_unset=True,
            response_model_exclude_none=True,
            methods=["GET"],
            endpoint=create_async_endpoint(
                self.client.conformance, self.conformance_get_model
            ),
        )

    def register_get_collections(self):
        """Register get collections endpoint (GET /collections).

        Returns:
            None
        """
        self.router.add_api_route(
            name="Get Collections",
            path="/collections",
            response_model=(
                Collections if self.settings.enable_response_models else None
            ),
            responses={
                200: {
                    "content": {
                        MimeTypes.json.value: {},
                        MimeTypes.html.value: {},
                    },
                    "model": Collections,
                },
            },
            response_class=self.response_class,
            response_model_exclude_unset=True,
            response_model_exclude_none=True,
            methods=["GET"],
            endpoint=create_async_endpoint(
                self.client.all_collections, self.collections_get_request_model
            ),
        )

    def register_get_collection(self):
        """Register get collection endpoint (GET /collection/{collection_id}).

        Returns:
            None
        """
        self.router.add_api_route(
            name="Get Collection",
            path="/collections/{collection_id}",
            response_model=api.Collection
            if self.settings.enable_response_models
            else None,
            responses={
                200: {
                    "content": {
                        MimeTypes.json.value: {},
                        MimeTypes.html.value: {},
                    },
                    "model": api.Collection,
                },
            },
            response_class=self.response_class,
            response_model_exclude_unset=True,
            response_model_exclude_none=True,
            methods=["GET"],
            endpoint=create_async_endpoint(
                self.client.get_collection, self.collection_get_request_model
            ),
        )

    def register_get_item_collection(self):
        """Register get item collection endpoint (GET /collection/{collection_id}/items).

        Returns:
            None
        """
        self.router.add_api_route(
            name="Get ItemCollection",
            path="/collections/{collection_id}/items",
            response_model=(
                api.ItemCollection if self.settings.enable_response_models else None
            ),
            responses={
                200: {
                    "content": {
                        MimeTypes.geojson.value: {},
                        MimeTypes.html.value: {},
                    },
                    "model": api.ItemCollection,
                },
            },
            response_class=GeoJSONResponse,
            response_model_exclude_unset=True,
            response_model_exclude_none=True,
            methods=["GET"],
            endpoint=create_async_endpoint(
                self.client.item_collection, self.items_get_request_model
            ),
        )

    def register_get_search(self):
        """Register search endpoint (GET /search).

        Returns:
            None
        """
        self.router.add_api_route(
            name="Search",
            path="/search",
            response_model=api.ItemCollection
            if self.settings.enable_response_models
            else None,
            responses={
                200: {
                    "content": {
                        MimeTypes.geojson.value: {},
                        MimeTypes.html.value: {},
                    },
                    "model": api.ItemCollection,
                },
            },
            response_class=GeoJSONResponse,
            response_model_exclude_unset=True,
            response_model_exclude_none=True,
            methods=["GET"],
            endpoint=create_async_endpoint(
                self.client.get_search, self.search_get_request_model
            ),
        )
