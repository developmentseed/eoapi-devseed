#!/usr/bin/env python3
"""Run eoAPI traffic simulations continuously with randomized intensity."""

from __future__ import annotations

import argparse
import asyncio
import random
import time
from dataclasses import dataclass

import simulate_traffic


@dataclass(frozen=True)
class TrafficProfile:
    name: str
    weight: int
    users: tuple[int, int]
    duration: tuple[int, int]
    think_min: tuple[float, float]
    think_max: tuple[float, float]
    pause: tuple[int, int]


PROFILES = [
    TrafficProfile("idle", 8, (1, 2), (3 * 60, 8 * 60), (3.0, 8.0), (10.0, 25.0), (60, 5 * 60)),
    TrafficProfile("easy", 35, (2, 5), (5 * 60, 15 * 60), (1.0, 4.0), (4.0, 12.0), (20, 2 * 60)),
    TrafficProfile("normal", 35, (5, 10), (5 * 60, 20 * 60), (0.4, 1.5), (2.5, 6.0), (10, 90)),
    TrafficProfile("heavy", 17, (10, 18), (3 * 60, 10 * 60), (0.1, 0.5), (0.8, 2.5), (10, 60)),
    TrafficProfile("burst", 5, (18, 30), (60, 3 * 60), (0.0, 0.2), (0.3, 1.2), (30, 3 * 60)),
]


def choose_profile() -> TrafficProfile:
    return random.choices(PROFILES, weights=[profile.weight for profile in PROFILES], k=1)[0]


def random_range(bounds: tuple[int, int] | tuple[float, float]) -> float:
    low, high = bounds
    return random.uniform(low, high)


async def run_forever(args: argparse.Namespace) -> None:
    base_url = args.base_url.rstrip("/")

    while True:
        profile = choose_profile()
        users = random.randint(*profile.users)
        duration = random.randint(*profile.duration)
        think_min = random_range(profile.think_min)
        think_max = max(think_min, random_range(profile.think_max))
        pause = random.randint(*profile.pause)

        print(
            f"Starting {profile.name} traffic: users={users}, duration={duration}s, "
            f"think={think_min:.1f}-{think_max:.1f}s, base_url={base_url}",
            flush=True,
        )

        run_args = argparse.Namespace(
            base_url=base_url,
            duration=float(duration),
            users=users,
            think_min=think_min,
            think_max=think_max,
            timeout=args.timeout,
            report_interval=args.report_interval,
        )
        started = time.monotonic()
        try:
            await simulate_traffic.run(run_args)
        except Exception as exc:  # noqa: BLE001 - keep the long-running loop alive.
            print(f"Traffic run failed: {exc!r}", flush=True)

        elapsed = time.monotonic() - started
        print(
            f"Finished {profile.name} traffic after {elapsed:.0f}s; "
            f"sleeping {pause}s before next run.",
            flush=True,
        )
        await asyncio.sleep(pause)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Continuously simulate randomized eoAPI demo traffic."
    )
    parser.add_argument(
        "--base-url",
        default=simulate_traffic.DEFAULT_BASE_URL,
        help=f"eoAPI base URL (default: {simulate_traffic.DEFAULT_BASE_URL})",
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
        default=60.0,
        help="Progress report interval in seconds (default: 60)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(run_forever(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", flush=True)


if __name__ == "__main__":
    main()
