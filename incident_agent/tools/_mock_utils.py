"""Shared helpers for the mocked infrastructure tools (Kubernetes/Kafka/
Postgres/Redis).

Every mock tool needs the same thing: deterministic-but-varied fake data,
so the same `pod_name`/`topic`/`service_name` always produces the same
scenario within a run (useful for a coherent demo/investigation) while
different names plausibly produce different failure modes (useful so the
mock data doesn't feel obviously canned). A single `pick_scenario()`
helper backs all four tools instead of each reimplementing hashing logic.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


def deterministic_rng(seed_key: str) -> random.Random:
    """A `random.Random` seeded from a stable hash of `seed_key`.

    Plain `random.Random(seed_key)` also works for `str` seeds, but going
    through an explicit sha256 hash avoids relying on Python's seed-hashing
    implementation detail for strings and makes the determinism contract
    explicit.
    """
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def pick_scenario(seed_key: str, options: Sequence[T]) -> T:
    """Deterministically pick one of `options` based on `seed_key`."""
    return options[deterministic_rng(seed_key).randrange(len(options))]
