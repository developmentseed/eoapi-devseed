#!/usr/bin/env python3
"""Generate realistic traffic against a local eoAPI stack for Grafana demos.

Emulates typical read-heavy usage across the landing page, STAC Browser paths,
STAC API, raster tiles, and vector features.

Example:
    uv run scripts/simulate_traffic.py
    uv run scripts/simulate_traffic.py --duration 5m --users 8
    uv run scripts/simulate_traffic.py --base-url http://127.0.0.1:8080 --duration 180
"""

from __future__ import annotations

import argparse
import asyncio
import random
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_COLLECTION = "noaa-emergency-response"
DEFAULT_ITEM = "20200307aC0853300w361200"
TILE = (15, 8589, 12849)
POINT = (-85.6358, 36.1624)

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
API_HEADERS = {"Accept": "application/json"}


def parse_duration(value: str) -> float:
    """Parse seconds or suffix forms like 3m, 90s, 1h."""
    value = value.strip().lower()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([smh])?", value)
    if not match:
        raise argparse.ArgumentTypeError(
            f"invalid duration {value!r}; use seconds or suffix s/m/h"
        )
    amount = float(match.group(1))
    unit = match.group(2) or "s"
    return amount * {"s": 1, "m": 60, "h": 3600}[unit]


@dataclass
class Context:
    base_url: str
    collection_id: str | None = None
    item_ids: list[str] = field(default_factory=list)
    search_id: str | None = None
    vector_collection: str = "pg_temp.pgstac_collections_view"
    vector_item_id: str | None = None
    has_stac_data: bool = False


@dataclass
class Stats:
    ok: int = 0
    errors: int = 0
    by_scenario: dict[str, int] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def record(self, scenario: str, *, success: bool) -> None:
        async with self.lock:
            self.by_scenario[scenario] = self.by_scenario.get(scenario, 0) + 1
            if success:
                self.ok += 1
            else:
                self.errors += 1


Scenario = Callable[[httpx.AsyncClient, Context, Stats], Awaitable[None]]


async def _request(
    client: httpx.AsyncClient,
    stats: Stats,
    scenario: str,
    method: str,
    url: str,
    *,
    expected: set[int] | None = None,
    **kwargs: Any,
) -> httpx.Response | None:
    expected = expected or {200}
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.HTTPError:
        await stats.record(scenario, success=False)
        return None

    success = response.status_code in expected
    await stats.record(scenario, success=success)
    return response


async def bootstrap(client: httpx.AsyncClient, ctx: Context) -> None:
    """Discover collections, items, and a raster search id from the live stack."""
    response = await client.get(
        f"{ctx.base_url}/stac/collections", headers=API_HEADERS, timeout=20
    )
    if response.status_code == 200:
        collections = response.json().get("collections") or []
        if collections:
            preferred = next(
                (
                    collection["id"]
                    for collection in collections
                    if collection.get("id") == DEFAULT_COLLECTION
                ),
                collections[0]["id"],
            )
            ctx.collection_id = preferred
            ctx.has_stac_data = True

            items_resp = await client.get(
                f"{ctx.base_url}/stac/collections/{ctx.collection_id}/items",
                params={"limit": 10},
                headers=API_HEADERS,
                timeout=20,
            )
            if items_resp.status_code == 200:
                features = items_resp.json().get("features") or []
                ctx.item_ids = [feature["id"] for feature in features[:10]]

    register_body = {
        "collections": [ctx.collection_id or DEFAULT_COLLECTION],
        "filter-lang": "cql-json",
    }

    register_resp = await client.post(
        f"{ctx.base_url}/raster/searches/register",
        json=register_body,
        headers=API_HEADERS,
        timeout=30,
    )
    if register_resp.status_code == 200:
        ctx.search_id = register_resp.json().get("id")

    vector_resp = await client.get(
        f"{ctx.base_url}/vector/collections", headers=API_HEADERS, timeout=20
    )
    if vector_resp.status_code == 200:
        collections = vector_resp.json().get("collections") or []
        ids = [collection["id"] for collection in collections]
        if "pg_temp.pgstac_collections_view" in ids:
            ctx.vector_collection = "pg_temp.pgstac_collections_view"
        elif ids:
            ctx.vector_collection = ids[0]

        items_resp = await client.get(
            f"{ctx.base_url}/vector/collections/{ctx.vector_collection}/items",
            params={"limit": 5},
            headers={"Accept": "application/geo+json"},
            timeout=20,
        )
        if items_resp.status_code == 200:
            features = items_resp.json().get("features") or []
            if features:
                ctx.vector_item_id = features[0]["id"]


async def scenario_landing(
    client: httpx.AsyncClient, ctx: Context, stats: Stats
) -> None:
    await _request(
        client,
        stats,
        "web.landing",
        "GET",
        f"{ctx.base_url}/",
        headers=BROWSER_HEADERS,
    )
    await _request(
        client,
        stats,
        "web.assets",
        "GET",
        f"{ctx.base_url}/assets/home.css",
        headers={"Accept": "text/css,*/*;q=0.1"},
    )
    await _request(
        client,
        stats,
        "web.assets",
        "GET",
        f"{ctx.base_url}/img/eoapi_logo_small.png",
        headers={"Accept": "image/*,*/*;q=0.8"},
    )


async def scenario_browser(
    client: httpx.AsyncClient, ctx: Context, stats: Stats
) -> None:
    await _request(
        client,
        stats,
        "web.browser",
        "GET",
        f"{ctx.base_url}/browser/",
        headers=BROWSER_HEADERS,
    )
    await _request(
        client,
        stats,
        "web.stac_viewer",
        "GET",
        f"{ctx.base_url}/stac/viewer",
        headers=BROWSER_HEADERS,
    )
    await _request(
        client,
        stats,
        "web.mosaic_builder",
        "GET",
        f"{ctx.base_url}/raster/searches/builder",
        headers=BROWSER_HEADERS,
    )


async def scenario_stac_catalog(
    client: httpx.AsyncClient, ctx: Context, stats: Stats
) -> None:
    await _request(
        client,
        stats,
        "stac.landing",
        "GET",
        f"{ctx.base_url}/stac/",
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "stac.conformance",
        "GET",
        f"{ctx.base_url}/stac/conformance",
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "stac.collections",
        "GET",
        f"{ctx.base_url}/stac/collections",
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "stac.queryables",
        "GET",
        f"{ctx.base_url}/stac/queryables",
        headers=API_HEADERS,
    )
    if not ctx.has_stac_data or not ctx.collection_id:
        return

    await _request(
        client,
        stats,
        "stac.collection",
        "GET",
        f"{ctx.base_url}/stac/collections/{ctx.collection_id}",
        headers=API_HEADERS,
    )


async def scenario_stac_items(
    client: httpx.AsyncClient, ctx: Context, stats: Stats
) -> None:
    if not ctx.has_stac_data or not ctx.collection_id:
        return

    item_id = random.choice(ctx.item_ids) if ctx.item_ids else DEFAULT_ITEM
    item_expected = {200} if ctx.item_ids else {200, 404}
    await _request(
        client,
        stats,
        "stac.items",
        "GET",
        f"{ctx.base_url}/stac/collections/{ctx.collection_id}/items",
        params={"limit": random.choice([1, 5, 10])},
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "stac.item",
        "GET",
        f"{ctx.base_url}/stac/collections/{ctx.collection_id}/items/{item_id}",
        headers=API_HEADERS,
        expected=item_expected,
    )
    await _request(
        client,
        stats,
        "stac.item_viewer",
        "GET",
        f"{ctx.base_url}/stac/collections/{ctx.collection_id}/items/{item_id}/viewer",
        headers=BROWSER_HEADERS,
        expected={200, 307, 308, 404},
    )


async def scenario_stac_search(
    client: httpx.AsyncClient, ctx: Context, stats: Stats
) -> None:
    params: dict[str, Any] = {"limit": random.choice([1, 5, 10])}
    body: dict[str, Any] = {"limit": random.choice([1, 5, 10])}
    if ctx.collection_id:
        params["collections"] = ctx.collection_id
        body["collections"] = [ctx.collection_id]

    await _request(
        client,
        stats,
        "stac.search_get",
        "GET",
        f"{ctx.base_url}/stac/search",
        params=params,
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "stac.search_post",
        "POST",
        f"{ctx.base_url}/stac/search",
        json=body,
        headers=API_HEADERS,
    )


async def scenario_raster(
    client: httpx.AsyncClient, ctx: Context, stats: Stats
) -> None:
    z, x, y = TILE
    lon, lat = POINT
    await _request(
        client,
        stats,
        "raster.health",
        "GET",
        f"{ctx.base_url}/raster/healthz",
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "raster.landing",
        "GET",
        f"{ctx.base_url}/raster/",
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "raster.searches",
        "GET",
        f"{ctx.base_url}/raster/searches",
        headers=API_HEADERS,
    )

    if ctx.search_id:
        await _request(
            client,
            stats,
            "raster.search_info",
            "GET",
            f"{ctx.base_url}/raster/searches/{ctx.search_id}/info",
            headers=API_HEADERS,
            timeout=30,
        )
        await _request(
            client,
            stats,
            "raster.search_tile_assets",
            "GET",
            f"{ctx.base_url}/raster/searches/{ctx.search_id}/tiles/WebMercatorQuad/{z}/{x}/{y}/assets",
            headers=API_HEADERS,
            timeout=30,
            expected={200, 404},
        )
        await _request(
            client,
            stats,
            "raster.search_tile",
            "GET",
            f"{ctx.base_url}/raster/searches/{ctx.search_id}/tiles/WebMercatorQuad/{z}/{x}/{y}",
            params={"assets": "cog"},
            headers={"Accept": "image/jpeg,image/png,*/*"},
            timeout=60,
            expected={200, 204, 404},
        )

    if not ctx.has_stac_data or not ctx.collection_id:
        return

    await _request(
        client,
        stats,
        "raster.point",
        "GET",
        f"{ctx.base_url}/raster/collections/{ctx.collection_id}/point/{lon},{lat}/assets",
        headers=API_HEADERS,
        timeout=30,
        expected={200, 404},
    )
    await _request(
        client,
        stats,
        "raster.tile_assets",
        "GET",
        f"{ctx.base_url}/raster/collections/{ctx.collection_id}/tiles/WebMercatorQuad/{z}/{x}/{y}/assets",
        headers=API_HEADERS,
        timeout=30,
        expected={200, 404},
    )
    await _request(
        client,
        stats,
        "raster.tile",
        "GET",
        f"{ctx.base_url}/raster/collections/{ctx.collection_id}/tiles/WebMercatorQuad/{z}/{x}/{y}",
        params={"assets": "cog"},
        headers={"Accept": "image/jpeg,image/png,*/*"},
        timeout=60,
        expected={200, 404},
    )

    if ctx.item_ids:
        item_id = random.choice(ctx.item_ids)
        await _request(
            client,
            stats,
            "raster.item_tilejson",
            "GET",
            f"{ctx.base_url}/raster/collections/{ctx.collection_id}/items/{item_id}/WebMercatorQuad/tilejson.json",
            headers=API_HEADERS,
            timeout=30,
            expected={200, 404},
        )


async def scenario_vector(
    client: httpx.AsyncClient, ctx: Context, stats: Stats
) -> None:
    await _request(
        client,
        stats,
        "vector.landing",
        "GET",
        f"{ctx.base_url}/vector/",
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "vector.conformance",
        "GET",
        f"{ctx.base_url}/vector/conformance",
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "vector.collections",
        "GET",
        f"{ctx.base_url}/vector/collections",
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "vector.collection",
        "GET",
        f"{ctx.base_url}/vector/collections/{ctx.vector_collection}",
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "vector.items",
        "GET",
        f"{ctx.base_url}/vector/collections/{ctx.vector_collection}/items",
        params={"limit": random.choice([1, 5, 10])},
        headers={"Accept": "application/geo+json"},
    )
    if ctx.vector_item_id:
        await _request(
            client,
            stats,
            "vector.item",
            "GET",
            f"{ctx.base_url}/vector/collections/{ctx.vector_collection}/items/{ctx.vector_item_id}",
            headers={"Accept": "application/geo+json"},
        )
    await _request(
        client,
        stats,
        "vector.tilejson",
        "GET",
        f"{ctx.base_url}/vector/collections/{ctx.vector_collection}/tiles/WebMercatorQuad/tilejson.json",
        headers=API_HEADERS,
    )
    await _request(
        client,
        stats,
        "vector.tile",
        "GET",
        f"{ctx.base_url}/vector/collections/public.my_data/tiles/WebMercatorQuad/0/0/0",
        headers={"Accept": "application/vnd.mapbox-vector-tile,*/*"},
        expected={200, 404},
    )


SCENARIOS: list[tuple[int, Scenario]] = [
    (12, scenario_landing),
    (10, scenario_browser),
    (18, scenario_stac_catalog),
    (20, scenario_stac_items),
    (15, scenario_stac_search),
    (18, scenario_raster),
    (7, scenario_vector),
]


async def user_loop(
    user_id: int,
    client: httpx.AsyncClient,
    ctx: Context,
    stats: Stats,
    stop_at: float,
    think_min: float,
    think_max: float,
) -> None:
    weights, scenarios = zip(*SCENARIOS)
    while time.monotonic() < stop_at:
        scenario = random.choices(scenarios, weights=weights, k=1)[0]
        await scenario(client, ctx, stats)
        await asyncio.sleep(random.uniform(think_min, think_max))


async def reporter(stats: Stats, stop_at: float, interval: float) -> None:
    start = time.monotonic()
    while time.monotonic() < stop_at:
        await asyncio.sleep(interval)
        elapsed = time.monotonic() - start
        async with stats.lock:
            total = stats.ok + stats.errors
            rate = total / elapsed if elapsed else 0.0
            print(
                f"[{elapsed:6.0f}s] requests={total:5d}  ok={stats.ok:5d}  "
                f"errors={stats.errors:3d}  rate={rate:5.1f}/s",
                flush=True,
            )


async def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    duration = args.duration
    stop_at = time.monotonic() + duration

    stats = Stats()
    ctx = Context(base_url=base_url)

    limits = httpx.Limits(max_connections=args.users * 4, max_keepalive_connections=args.users * 2)
    timeout = httpx.Timeout(args.timeout, connect=10.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout, follow_redirects=True) as client:
        print(f"Bootstrapping against {base_url} ...", flush=True)
        try:
            await bootstrap(client, ctx)
        except httpx.HTTPError as exc:
            print(f"Bootstrap warning: {exc}", file=sys.stderr)

        print(
            f"Using collection={ctx.collection_id!r}, items={len(ctx.item_ids)}, "
            f"search_id={ctx.search_id!r}, stac_data={ctx.has_stac_data}",
            flush=True,
        )
        print(
            f"Running {args.users} virtual users for {duration:.0f}s "
            f"(think {args.think_min:.1f}-{args.think_max:.1f}s between scenarios)",
            flush=True,
        )

        tasks = [
            asyncio.create_task(
                user_loop(
                    user_id,
                    client,
                    ctx,
                    stats,
                    stop_at,
                    args.think_min,
                    args.think_max,
                )
            )
            for user_id in range(args.users)
        ]
        tasks.append(asyncio.create_task(reporter(stats, stop_at, args.report_interval)))

        await asyncio.gather(*tasks)

    elapsed = duration
    total = stats.ok + stats.errors
    print("\nDone.", flush=True)
    print(
        f"Total requests: {total} ({stats.ok} ok, {stats.errors} errors) "
        f"over {elapsed:.0f}s ({total / elapsed:.1f}/s avg)",
        flush=True,
    )
    print("Top scenarios:", flush=True)
    for name, count in sorted(stats.by_scenario.items(), key=lambda item: item[1], reverse=True)[:12]:
        print(f"  {name:22s} {count}", flush=True)

    return 1 if stats.errors and stats.ok == 0 else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulate typical eoAPI traffic for Grafana dashboard demos."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"eoAPI base URL via Traefik (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--duration",
        type=parse_duration,
        default=parse_duration("3m"),
        help="Run time in seconds or with suffix s/m/h (default: 3m)",
    )
    parser.add_argument(
        "--users",
        type=int,
        default=6,
        help="Concurrent virtual users (default: 6)",
    )
    parser.add_argument(
        "--think-min",
        type=float,
        default=0.4,
        help="Minimum pause between scenario batches per user (default: 0.4s)",
    )
    parser.add_argument(
        "--think-max",
        type=float,
        default=2.5,
        help="Maximum pause between scenario batches per user (default: 2.5s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Per-request timeout in seconds (default: 45)",
    )
    parser.add_argument(
        "--report-interval",
        type=float,
        default=15.0,
        help="Progress report interval in seconds (default: 15)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.users < 1:
        parser.error("--users must be at least 1")
    if args.think_min < 0 or args.think_max < args.think_min:
        parser.error("--think-min/--think-max are invalid")

    try:
        raise SystemExit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        print("\nInterrupted.", flush=True)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
