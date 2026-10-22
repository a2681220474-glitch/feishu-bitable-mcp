"""Conservative record validation against the live field schema."""

from __future__ import annotations

import json
import math
from typing import Any
from urllib.parse import urlsplit

from .config import BitableError


def validate_fields(values: dict[str, Any], schema: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(values, dict) or not 1 <= len(values) <= 100:
        raise BitableError("fields must contain between 1 and 100 field-name/value entries.")
    try:
        size = len(json.dumps(values, ensure_ascii=False, allow_nan=False).encode())
    except (TypeError, ValueError):
        raise BitableError("fields must contain finite, JSON-serializable values.") from None
    if size > 50_000:
        raise BitableError("The serialized fields payload must not exceed 50000 bytes.")
    by_name = {x.get("field_name"): x for x in schema}
    validated: dict[str, Any] = {}
    for name, value in values.items():
        if not isinstance(name, str) or name not in by_name:
            raise BitableError("Unknown field name. Call list_fields and use exact field names.")
        raw = by_name[name]
        kind = raw.get("type")
        config = raw.get("property") or {}
        if kind in {1, 13}:
            valid = isinstance(value, str) and len(value) <= 5000
        elif kind == 2:
            try:
                valid = type(value) in {int, float} and math.isfinite(value)
            except OverflowError:
                valid = False
        elif kind == 7:
            valid = type(value) is bool
        elif kind == 5:
            valid = type(value) is int and 0 <= value <= 253_402_300_799_999
        elif kind in {3, 4}:
            options = {x.get("name") for x in config.get("options", []) if isinstance(x, dict)}
            choices = value if kind == 4 else [value]
            valid = (
                isinstance(choices, list)
                and len(choices) <= 100
                and all(isinstance(x, str) and x in options for x in choices)
            )
            if valid and kind == 4:
                valid = len(set(choices)) == len(choices)
        elif kind == 15:
            valid = (
                isinstance(value, dict)
                and set(value) == {"text", "link"}
                and all(isinstance(x, str) for x in value.values())
            )
            if valid:
                try:
                    link = urlsplit(value["link"])
                    valid = (
                        link.scheme in {"https", "http"}
                        and bool(link.hostname)
                        and link.username is None
                        and not any(ord(c) <= 32 or ord(c) == 127 for c in value["link"])
                        and "\\" not in value["link"]
                    )
                    if link.port is not None and not 1 <= link.port <= 65535:
                        valid = False
                except ValueError:
                    valid = False
        else:
            raise BitableError(
                "Field type is read-only or unsupported for creation. "
                "Supported: text, phone, number, checkbox, date-time, static select and URL."
            )
        if not valid:
            raise BitableError(
                "Field value does not match its live field type or configured options."
            )
        validated[name] = value
    return validated
