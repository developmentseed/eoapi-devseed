"""Optional Prometheus metrics for the vector service."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import Info
from starlette.responses import Response

if TYPE_CHECKING:
    from fastapi import FastAPI

_INSTRUMENTED_APPS: set[int] = set()

_ROUTE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/$"), "landing"),
    (re.compile(r"^/conformance$"), "conformance"),
    (re.compile(r"^/collections$"), "list_collections"),
    (re.compile(r"^/collections/[^/]+$"), "get_collection"),
    (re.compile(r"^/collections/[^/]+/items$"), "list_items"),
    (re.compile(r"^/collections/[^/]+/items/[^/]+$"), "get_item"),
    (re.compile(r"/tiles/"), "tiles"),
    (re.compile(r"^/tileMatrixSets"), "tile_matrix_sets"),
]


def resolve_operation(method: str, route: str | None) -> str:
    """Map a request to a low-cardinality vector operation label."""
    if not route or route == "none":
        return "unknown"

    for pattern, operation in _ROUTE_RULES:
        if pattern.search(route):
            return operation

    return "other"


def _metric_or_none(factory):
    try:
        return factory()
    except ValueError as exc:
        if "Duplicated time series in CollectorRegistry" not in str(exc):
            raise
        return None


REQUESTS = _metric_or_none(
    lambda: Counter(
        "http_requests_total",
        "Total HTTP requests by vector operation.",
        labelnames=("operation", "method", "status"),
        registry=REGISTRY,
    )
)
LATENCY = _metric_or_none(
    lambda: Histogram(
        "http_request_duration_seconds",
        "HTTP request latency by vector operation.",
        labelnames=("operation", "method"),
        buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, float("inf")),
        registry=REGISTRY,
    )
)


def record_service_metrics(info: Info) -> None:
    """Record request count and latency using low-cardinality operation labels."""
    route = info.request.scope.get("route")
    route_path = getattr(route, "path", None)
    operation = resolve_operation(info.method, route_path)

    if REQUESTS is not None:
        REQUESTS.labels(operation, info.method, info.modified_status).inc()
    if LATENCY is not None:
        LATENCY.labels(operation, info.method).observe(info.modified_duration)


def _metrics_response() -> Response:
    if multiproc_dir := os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry, path=multiproc_dir)
        data = generate_latest(registry)
    else:
        data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


def instrument_app(app: FastAPI, endpoint: str = "/metrics") -> None:
    """Instrument a FastAPI app and expose Prometheus metrics."""
    if id(app) in _INSTRUMENTED_APPS:
        return

    (
        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            excluded_handlers=[r"/healthz", r"/metrics"],
        )
        .add(record_service_metrics)
        .instrument(app)
    )

    @app.get(endpoint, include_in_schema=False)
    async def metrics() -> Response:
        return _metrics_response()

    _INSTRUMENTED_APPS.add(id(app))
