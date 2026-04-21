from __future__ import annotations

import json
from typing import Any

from jsonschema import ValidationError, validate


class StructuredOutputError(ValueError):
    """Raised when a model response cannot be parsed into the requested JSON shape."""

    def __init__(
        self,
        message: str,
        *,
        raw_text: str | None = None,
        raw_data: Any | None = None,
        validation_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.raw_data = raw_data
        self.validation_message = validation_message


def extract_json_value(content: str) -> Any:
    raw = content.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        object_start = raw.find("{")
        object_end = raw.rfind("}")
        array_start = raw.find("[")
        array_end = raw.rfind("]")

        candidate = ""
        if object_start != -1 and object_end != -1 and object_end > object_start:
            candidate = raw[object_start : object_end + 1]
        elif array_start != -1 and array_end != -1 and array_end > array_start:
            candidate = raw[array_start : array_end + 1]

        if not candidate:
            raise StructuredOutputError(
                "Model did not return valid JSON",
                raw_text=content,
            )

        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(
                "Model did not return valid JSON",
                raw_text=content,
            ) from exc


def validate_structured_payload(
    payload: Any,
    schema: dict[str, Any],
    *,
    raw_text: str | None = None,
) -> dict[str, Any]:
    try:
        validate(instance=payload, schema=schema)
    except ValidationError as exc:
        raise StructuredOutputError(
            "Model JSON did not match the requested schema",
            raw_text=raw_text,
            raw_data=payload,
            validation_message=exc.message,
        ) from exc

    if not isinstance(payload, dict):
        raise StructuredOutputError(
            "Structured output must be a JSON object",
            raw_text=raw_text,
            raw_data=payload,
        )
    return payload


def parse_and_validate_json(content: str, schema: dict[str, Any]) -> dict[str, Any]:
    parsed = extract_json_value(content)
    return validate_structured_payload(parsed, schema, raw_text=content)
