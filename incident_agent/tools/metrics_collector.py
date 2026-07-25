"""Metrics Collector tool -- mocked time-series telemetry.

Distinct from the Postgres/Redis mock tools (which return a *current
snapshot* of health stats): this tool returns a *time series* over a
window, which is what trend detection (the Metrics Analysis Agent's job)
actually needs. Series are generated deterministically per
`(component, metric_name)` -- same inputs always produce the same shape --
so a demo/test run is reproducible, but with a built-in "degrading trend
approaching threshold" pattern that resembles a real incident rather than
flat noise.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from incident_agent.models.tool_results import MetricSample
from incident_agent.tools.base import run_structured

_MetricProfile = dict[str, float | str]

_METRIC_PROFILES: dict[tuple[str, str], _MetricProfile] = {
    ("kubernetes", "memory_usage_percent"): {"baseline": 55.0, "threshold": 90.0, "unit": "percent"},
    ("kubernetes", "cpu_usage_percent"): {"baseline": 40.0, "threshold": 85.0, "unit": "percent"},
    ("kubernetes", "restart_count"): {"baseline": 0.0, "threshold": 3.0, "unit": "count"},
    ("kafka", "consumer_lag"): {"baseline": 120.0, "threshold": 5000.0, "unit": "messages"},
    ("kafka", "under_replicated_partitions"): {"baseline": 0.0, "threshold": 1.0, "unit": "count"},
    ("database", "connection_pool_utilization_percent"): {"baseline": 45.0, "threshold": 95.0, "unit": "percent"},
    ("database", "query_latency_ms"): {"baseline": 25.0, "threshold": 500.0, "unit": "milliseconds"},
    ("cache", "eviction_rate_per_min"): {"baseline": 2.0, "threshold": 200.0, "unit": "events_per_minute"},
    ("application", "http_5xx_rate_percent"): {"baseline": 0.1, "threshold": 5.0, "unit": "percent"},
}
_DEFAULT_PROFILE: _MetricProfile = {"baseline": 50.0, "threshold": 100.0, "unit": "unitless"}


def _generate_series(
    component: str, metric_name: str, window_minutes: int, interval_seconds: int
) -> list[MetricSample]:
    profile = _METRIC_PROFILES.get((component, metric_name), _DEFAULT_PROFILE)
    baseline, threshold = float(profile["baseline"]), float(profile["threshold"])
    unit = str(profile["unit"])

    rng = random.Random(f"{component}:{metric_name}:{window_minutes}:{interval_seconds}")
    num_points = max(2, (window_minutes * 60) // max(interval_seconds, 1))
    now = datetime.now(timezone.utc)

    samples: list[MetricSample] = []
    for i in range(num_points):
        progress = i / (num_points - 1)
        # Ramp from baseline toward ~1.3x threshold across the window, plus noise --
        # models a metric actively degrading toward the moment of investigation.
        trend_value = baseline + progress * (threshold * 1.3 - baseline)
        noisy_value = max(0.0, trend_value + rng.uniform(-0.05, 0.05) * threshold)
        timestamp = now - timedelta(seconds=(num_points - 1 - i) * interval_seconds)
        samples.append(
            MetricSample(
                metric_name=metric_name,
                value=round(noisy_value, 2),
                unit=unit,
                timestamp=timestamp,
                labels={"component": component},
                is_anomalous=noisy_value > threshold,
                threshold=threshold,
            )
        )
    return samples


def _collect(component: str, metric_name: str, window_minutes: int, interval_seconds: int) -> dict:
    samples = _generate_series(component, metric_name, window_minutes, interval_seconds)
    return {
        "component": component,
        "metric_name": metric_name,
        "window_minutes": window_minutes,
        "sample_count": len(samples),
        "latest_value": samples[-1].value,
        "threshold_breached": samples[-1].is_anomalous,
        "samples": [sample.model_dump(mode="json") for sample in samples],
    }


@tool
def metrics_collector(
    component: str,
    metric_name: str,
    window_minutes: int = 15,
    interval_seconds: int = 60,
) -> str:
    """Collect a recent time series of a metric for a component (mocked telemetry).

    Known `(component, metric_name)` pairs use a realistic baseline/threshold
    profile (e.g. `('kubernetes', 'memory_usage_percent')`); unknown pairs
    fall back to a generic 0-100 profile. `component` is typically one of
    kubernetes, kafka, database, cache, application.
    """
    return run_structured(
        "metrics_collector",
        lambda: _collect(component, metric_name, window_minutes, interval_seconds),
    )
