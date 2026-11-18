"""Granular-scope Base v3 record reads, with explicit offset/revision cursors."""

from __future__ import annotations

import base64
import hashlib
import json

from .config import BitableError


def granular_records(settings, *, continuing=False):
    if settings.identity != "user":
        return False
    from fastmcp.server.dependencies import get_access_token

    access = get_access_token()
    scopes = (access.claims or {}).get("feishu_granted_scopes", []) if access else []
    return "base:record:read" in scopes and (
        continuing
        or not {
            "bitable:app",
            "bitable:app:readonly",
            "base:record:retrieve",
        }.intersection(scopes)
    )


async def records(api, target, page_size, page_token):
    from fastmcp.server.dependencies import get_access_token

    access = get_access_token()
    if access is None or not access.subject:
        raise BitableError("A verified user identity is required for Base v3 reads.")
    binding = hashlib.sha256(
        json.dumps(
            {
                "target": target.identifiers(),
                "subject": access.subject,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    offset, expected_revision = 0, None
    if page_token:
        try:
            if not page_token.startswith("v3."):
                raise ValueError
            value = json.loads(
                base64.urlsafe_b64decode(page_token[3:] + "=" * (-len(page_token[3:]) % 4))
            )
            if (
                set(value) != {"target", "offset", "rev"}
                or value["target"] != binding
                or type(value["offset"]) is not int
                or not 1 <= value["offset"] <= 1_000_000_000
                or type(value["rev"]) is not int
                or value["rev"] < 0
            ):
                raise ValueError
            offset, expected_revision = value["offset"], value["rev"]
        except (ValueError, TypeError, KeyError):
            raise BitableError(
                "Invalid Base v3 cursor or a different table/view; start again."
            ) from None
    limit = min(page_size, 200)
    params = {"limit": limit, "offset": offset}
    if target.view_id:
        params["view_id"] = target.view_id
    data = await api.request(
        "GET",
        f"/base/v3/bases/{target.app_token}/tables/{target.table_id}/records",
        params=params,
    )
    names, rows, ids = data.get("fields"), data.get("data"), data.get("record_id_list")
    revision = data.get("rev")
    if (
        not isinstance(names, list)
        or not all(isinstance(x, str) for x in names)
        or len(set(names)) != len(names)
        or not isinstance(rows, list)
        or not isinstance(ids, list)
        or len(ids) != len(rows)
        or not all(isinstance(x, str) and x for x in ids)
        or len(set(ids)) != len(ids)
        or not all(isinstance(row, list) and len(row) == len(names) for row in rows)
        or type(revision) is not int
        or revision < 0
    ):
        raise BitableError("Feishu returned an invalid Base v3 record matrix.")
    if expected_revision is not None and revision != expected_revision:
        raise BitableError("Base revision changed between record pages; restart pagination.")
    more = data.get("has_more")
    if type(more) is not bool or more and not rows:
        raise BitableError("Base v3 pagination did not advance.")
    next_token = None
    if more:
        value = {"target": binding, "offset": offset + len(rows), "rev": revision}
        next_token = "v3." + base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip(
            "="
        )
    return {
        **data,  # Keep the original matrix, field IDs/types, revision and unknown metadata.
        "records": [
            {"record_id": rid, "fields": dict(zip(names, row, strict=True))}
            for rid, row in zip(ids, rows, strict=True)
        ],
        "has_more": more,
        "page_token": next_token,
        "api_version": "base/v3",
        "effective_page_size": limit,
        "observed_record_count": offset + len(rows) if not more else None,
        "pagination_note": "Offset cursor is bound to table/view and revision. "
        "Restart after external edits; no upstream total is invented.",
    }
