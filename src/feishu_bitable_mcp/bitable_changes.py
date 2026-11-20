"""Named Bitable mutations with schema validation and optimistic preflight checks."""

from __future__ import annotations

import re
import uuid

from .change_policy import OPERATIONS, target_key
from .changes import fingerprint
from .config import BitableError, Target
from .writes import validate_fields


def name(value, maximum=255):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BitableError("Provide a nonempty name within the documented length limit.")
    if any(ord(c) < 32 for c in value):
        raise BitableError("Names cannot contain control characters.")
    return value


def field_definition(value):
    if not isinstance(value, dict) or set(value) - {"field_name", "type", "property"}:
        raise BitableError("Field definitions accept field_name, type and property only.")
    name(value.get("field_name"), 100)
    if type(value.get("type")) is not int or value["type"] not in {1, 2, 3, 4, 5, 7, 13, 15}:
        raise BitableError(
            "Field creation currently supports text, number, select, date, checkbox, phone and URL."
        )
    if "property" in value:
        config = value["property"]
        if (
            value["type"] not in {3, 4}
            or not isinstance(config, dict)
            or set(config) != {"options"}
        ):
            raise BitableError("Only select options are supported in field property for now.")
        options = config["options"]
        if not isinstance(options, list) or not 1 <= len(options) <= 100:
            raise BitableError("Provide 1-100 named select options.")
        for option in options:
            if not isinstance(option, dict) or set(option) != {"name"}:
                raise BitableError("Each new select option accepts a name only.")
            name(option["name"], 100)
        if len({x["name"] for x in options}) != len(options):
            raise BitableError("Select option names must be unique.")
    return value


class BitableChanges:
    def __init__(self, api):
        self.api = api

    async def snapshot(self, spec):
        if not spec:
            return None
        target = Target(spec["app"], spec["table"])
        schema = await self.api.fields(target)
        records = []
        for record_id in spec.get("records", []):
            data = await self.api.request(
                "GET", self.api.table_route(target, f"/records/{record_id}")
            )
            if not isinstance(data.get("record"), dict):
                raise BitableError("Cannot verify current record before update.")
            records.append(data["record"])
        return {"schema": schema, "records": records}

    async def prepare(self, operation, url, payload, request_id):
        spec = OPERATIONS[operation]
        _, parent, table_id = target_key(url, spec.target_kind)
        method, query, snapshot_spec, snapshot = "POST", {}, None, None
        if operation in {"bitable.create_records", "bitable.update_records"}:
            if set(payload) != {"records"}:
                raise BitableError("Record changes require records only.")
            rows = payload["records"]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
                raise BitableError("A record change accepts 1-100 records.")
            updating = operation == "bitable.update_records"
            record_ids = []
            for row in rows:
                keys = {"record_id", "fields"} if updating else {"fields"}
                if not isinstance(row, dict) or set(row) != keys:
                    raise BitableError("Use exact record_id/fields entries for this operation.")
                if updating:
                    rid = row["record_id"]
                    if not isinstance(rid, str) or not re.fullmatch(r"rec[A-Za-z0-9]{7,100}", rid):
                        raise BitableError("Invalid record_id.")
                    record_ids.append(rid)
            if len(set(record_ids)) != len(record_ids):
                raise BitableError("Duplicate record_id in a batch.")
            snapshot_spec = {"app": parent, "table": table_id, "records": record_ids}
            snapshot = await self.snapshot(snapshot_spec)
            validated = []
            for row in rows:
                fields = validate_fields(row["fields"], snapshot["schema"])
                validated.append(
                    ({"record_id": row["record_id"]} if updating else {})
                    | {
                        "fields": fields,
                    }
                )
            suffix = "batch_update" if updating else "batch_create"
            route = f"/bitable/v1/apps/{parent}/tables/{table_id}/records/{suffix}"
            if not updating:
                query["client_token"] = str(uuid.uuid4())
            body = {"records": validated}
        elif operation == "bitable.create_base":
            if set(payload) != {"name"}:
                raise BitableError("Base creation accepts name only.")
            route = "/bitable/v1/apps"
            body = {"name": name(payload["name"]), "folder_token": parent}
        elif operation == "bitable.create_table":
            if set(payload) - {"name", "fields"} or "name" not in payload:
                raise BitableError("Table creation accepts name and optional fields.")
            title = name(payload["name"], 100)
            if any(c in title for c in "/\\?*:[]"):
                raise BitableError("Table name contains a forbidden character.")
            table = {"name": title}
            if "fields" in payload:
                if (
                    not isinstance(payload["fields"], list)
                    or not 1 <= len(payload["fields"]) <= 100
                ):
                    raise BitableError("Provide 1-100 initial fields.")
                table["fields"] = [field_definition(x) for x in payload["fields"]]
                if table["fields"][0]["type"] not in {1, 2, 5, 13, 15}:
                    raise BitableError("Choose a supported primary field type for the first field.")
            route, body = f"/bitable/v1/apps/{parent}/tables", {"table": table}
        elif operation == "bitable.create_field":
            route = f"/bitable/v1/apps/{parent}/tables/{table_id}/fields"
            body = field_definition(payload)
            snapshot_spec = {"app": parent, "table": table_id}
            snapshot = await self.snapshot(snapshot_spec)
            if any(x.get("field_name") == body["field_name"] for x in snapshot["schema"]):
                raise BitableError("A field with this name already exists.")
        else:
            raise BitableError("No adapter for this operation.")
        return {
            "operation": operation,
            "method": method,
            "route": route,
            "body": body,
            "query": query,
            "snapshot_spec": snapshot_spec,
            "snapshot": fingerprint(snapshot),
            "preconditions": {
                "optimistic_snapshot": fingerprint(snapshot),
                "atomic_compare_and_swap": False,
                "note": "MCP operations are serialized; external writers can still race this API.",
            },
        }

    async def check(self, prepared):
        if fingerprint(await self.snapshot(prepared["snapshot_spec"])) != prepared["snapshot"]:
            raise BitableError("Resource or schema changed after preview; prepare again.")

    async def dispatch(self, prepared):
        data = await self.api.request(
            prepared["method"],
            prepared["route"],
            params=prepared["query"],
            json=prepared["body"],
        )
        operation = prepared["operation"]
        if operation.endswith("_records"):
            records = data.get("records")
            if not isinstance(records, list) or len(records) != len(prepared["body"]["records"]):
                raise BitableError(
                    "Write response did not confirm all records; inspect before retrying."
                )
            ids = [x.get("record_id") for x in records if isinstance(x, dict)]
            if len(ids) != len(records) or not all(isinstance(x, str) and x for x in ids):
                raise BitableError(
                    "Write response has invalid record IDs; inspect before retrying."
                )
            if len(set(ids)) != len(ids):
                raise BitableError("Write response repeats record IDs; inspect before retrying.")
            if operation == "bitable.update_records" and set(ids) != {
                row["record_id"] for row in prepared["body"]["records"]
            }:
                raise BitableError("Write response does not confirm the exact updated record IDs.")
            return {"operation": operation, "record_ids": ids, "count": len(ids)}
        key = {
            "bitable.create_base": "app",
            "bitable.create_table": "table_id",
            "bitable.create_field": "field",
        }[operation]
        value = data.get(key)
        if key == "app" and isinstance(value, dict):
            value = value.get("app_token")
        elif key == "field" and isinstance(value, dict):
            value = value.get("field_id")
        if not isinstance(value, str) or not value:
            raise BitableError(
                "Creation response has no confirmed resource ID; inspect before retrying."
            )
        return {"operation": operation, "resource_id": value}
