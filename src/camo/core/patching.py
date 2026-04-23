from __future__ import annotations

from copy import deepcopy
from typing import Any

from deepdiff import DeepDiff


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def build_structured_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    diff = DeepDiff(before, after, ignore_order=True).to_dict()
    return _stringify_keys(diff)


def _stringify_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stringify_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stringify_keys(item) for item in value]
    return value
