"""Operator policy for named mutations; no client-supplied API routes or scopes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .config import BitableError, Target


@dataclass(frozen=True)
class Operation:
    access: str
    target_kind: str
    scopes: tuple[str, ...]


# Official API/CLI sources and scoped live smoke tests; see docs/write-api-review.md.
OPERATIONS = {
    "bitable.create_records": Operation("write", "table", ("base:record:create", "bitable:app")),
    "bitable.update_records": Operation("write", "table", ("base:record:update", "bitable:app")),
    "bitable.create_base": Operation("create", "folder", ("base:app:create", "bitable:app")),
    "bitable.create_table": Operation("create", "base", ("base:table:create", "bitable:app")),
    "bitable.create_field": Operation("create", "table", ("base:field:create", "bitable:app")),
    "document.create": Operation("create", "folder", ("docx:document:create", "docx:document")),
    "document.insert_text": Operation(
        "write", "docx", ("docx:document:write_only", "docx:document")
    ),
    "document.replace_text": Operation(
        "write", "docx", ("docx:document:write_only", "docx:document")
    ),
    "sheets.create": Operation(
        "create",
        "folder",
        ("sheets:spreadsheet:create", "sheets:spreadsheet", "drive:drive"),
    ),
    "sheets.add_worksheet": Operation(
        "create",
        "sheets",
        ("sheets:spreadsheet:write_only", "sheets:spreadsheet", "drive:drive"),
    ),
    "sheets.write_cells": Operation(
        "write",
        "sheets",
        ("sheets:spreadsheet:write_only", "sheets:spreadsheet", "drive:drive"),
    ),
    "sheets.append_cells": Operation(
        "write",
        "sheets",
        ("sheets:spreadsheet:write_only", "sheets:spreadsheet", "drive:drive"),
    ),
    "sheets.format_cells": Operation(
        "write",
        "sheets",
        ("sheets:spreadsheet:write_only", "sheets:spreadsheet", "drive:drive"),
    ),
    "excel.create": Operation(
        "create", "folder", ("drive:file:upload", "drive:file", "drive:drive")
    ),
    "excel.edit": Operation("write", "file", ("drive:file:upload", "drive:file", "drive:drive")),
}
WRITE_SCOPES = frozenset(scope for op in OPERATIONS.values() for scope in op.scopes)


def target_key(url: str, kind: str) -> tuple[str, str, str]:
    if kind == "table":
        target = Target.parse(url)
        return kind, target.app_token, target.table_id
    if kind in {"docx", "sheets", "file"}:
        from .resources import Resource

        resource = Resource.parse(url)
        if resource.kind != kind:
            raise BitableError(f"This operation requires a direct Feishu {kind} URL.")
        return kind, resource.token, (resource.sheet_id or "") if kind == "sheets" else ""
    if kind not in {"base", "folder"}:
        raise BitableError("Unknown resource kind.")
    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) <= 32 for c in url):
        raise BitableError("Use a complete HTTPS Feishu target URL.")
    try:
        parts = urlsplit(url)
        route = "/base/" if kind == "base" else "/drive/folder/"
        match = re.fullmatch(re.escape(route) + r"([A-Za-z0-9]{10,100})/?", parts.path)
        query = parse_qs(parts.query, keep_blank_values=True, max_num_fields=30)
        valid = (
            match
            and parts.scheme == "https"
            and re.fullmatch(r"(?:[a-z0-9-]+\.)*feishu\.cn", parts.hostname or "")
            and parts.username is None
            and parts.password is None
            and parts.port is None
            and not parts.fragment
            and "\\" not in url
            and "\x7f" not in url
            and not {"table", "view"}.intersection(query)
        )
    except ValueError:
        valid = False
    if not valid:
        raise BitableError("Use an exact Feishu Base URL or Drive folder URL for creation.")
    return kind, match[1], ""


def validate_policy(policy: dict) -> None:
    if not isinstance(policy, dict) or not policy:
        raise BitableError("FEISHU_CHANGE_ALLOWLIST must contain operation-to-URL lists.")
    for name, urls in policy.items():
        if name not in OPERATIONS or not isinstance(urls, list) or not urls:
            raise BitableError("Unknown operation or empty URL list in FEISHU_CHANGE_ALLOWLIST.")
        for url in urls:
            target_key(url, OPERATIONS[name].target_kind)


def authorize(policy: dict, operation: str, url: str) -> Operation:
    if operation not in OPERATIONS:
        raise BitableError("Unsupported change operation.")
    spec = OPERATIONS[operation]
    key = target_key(url, spec.target_kind)
    if key not in {target_key(x, spec.target_kind) for x in policy.get(operation, [])}:
        raise BitableError("This operation and exact resource are not operator-authorized.")
    return spec
