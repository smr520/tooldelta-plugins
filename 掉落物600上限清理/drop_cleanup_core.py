"""Pure command helpers for the dropped-item cleanup plugin."""

from __future__ import annotations

import json
from typing import Any, Iterable


DIMENSIONS = ("overworld", "nether", "the_end")


def validate_threshold(threshold: Any, default: int = 600) -> int:
    try:
        return max(1, int(threshold))
    except (TypeError, ValueError, OverflowError):
        return default


def build_count_command(
    dimension: str,
    threshold: int = 600,
) -> str:
    limit = validate_threshold(threshold) + 1
    return f"/execute in {dimension} run testfor @e[type=item,c={limit}]"


def build_cleanup_command(dimension: str) -> str:
    return f"/execute in {dimension} run kill @e[type=item]"


def _field(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _decode_dataset(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped[:1] not in {"{", "["}:
        return value
    try:
        return json.loads(stripped)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value


def extract_success_count(response: Any) -> int | None:
    if response is None:
        return None
    dataset = _decode_dataset(_field(response, "DataSet", default=response))
    if isinstance(dataset, dict) and "Val" in dataset:
        dataset = _decode_dataset(dataset["Val"])
    value = _field(dataset, "SuccessCount", "successCount", default=None)
    if value is None:
        value = _field(response, "SuccessCount", "successCount", default=None)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return None


def total_dropped_items(
    counts: Iterable[int],
) -> int:
    return sum(max(0, int(count)) for count in counts)


def should_cleanup(
    counts: Iterable[int],
    threshold: Any = 600,
) -> bool:
    return total_dropped_items(counts) > validate_threshold(threshold)
