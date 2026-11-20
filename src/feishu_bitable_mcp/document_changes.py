"""Small, explicit Docx text operations; arbitrary block mutations are not accepted."""

from __future__ import annotations

import re
import uuid

from .bitable_changes import name
from .change_policy import OPERATIONS, target_key
from .changes import fingerprint
from .config import BitableError


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9]{10,100}", value):
        raise BitableError("Choose a valid block_id from read_document.")
    return value


def text_elements(text):
    if not isinstance(text, str) or not text or re.search(r"[\ud800-\udfff]", text):
        raise BitableError("Each paragraph needs valid nonempty Unicode text.")
    if len(text.encode("utf-16-le")) > 20000:
        raise BitableError("Each paragraph needs 1-10000 UTF-16 characters.")
    if any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise BitableError("Text contains unsupported control characters.")
    return [{"text_run": {"content": text}}]


class DocumentChanges:
    def __init__(self, api):
        self.api = api

    async def snapshot(self, spec):
        if not spec:
            return None
        route = f"/docx/v1/documents/{spec['document']}"
        data = await self.api.request("GET", route)
        revision = data.get("document", {}).get("revision_id")
        if type(revision) is not int or revision < 1:
            raise BitableError("Cannot verify the current document revision.")
        block = await self.api.request(
            "GET", route + f"/blocks/{spec['block']}", params={"document_revision_id": revision}
        )
        if not isinstance(block.get("block"), dict):
            raise BitableError("Cannot verify the selected document block.")
        return {"revision": revision, "block": block["block"]}

    async def prepare(self, operation, url, payload, request_id):
        _, token, _ = target_key(url, OPERATIONS[operation].target_kind)
        snapshot_spec, snapshot, query = None, None, {}
        if operation == "document.create":
            if set(payload) != {"title"}:
                raise BitableError("Document creation accepts title only.")
            method, route = "POST", "/docx/v1/documents"
            body = {"title": name(payload["title"], 800), "folder_token": token}
        else:
            route = f"/docx/v1/documents/{token}/blocks/"
            if operation == "document.insert_text":
                if (
                    set(payload) - {"parent_block_id", "index", "paragraphs"}
                    or "paragraphs" not in payload
                ):
                    raise BitableError(
                        "Insert accepts paragraphs, optional parent_block_id and index."
                    )
                parent = identifier(payload.get("parent_block_id", token))
                paragraphs = payload["paragraphs"]
                index = payload.get("index", -1)
                if not isinstance(paragraphs, list) or not 1 <= len(paragraphs) <= 50:
                    raise BitableError("Insert 1-50 paragraphs per confirmed operation.")
                if type(index) is not int or index < -1:
                    raise BitableError("index must be -1 (append) or a nonnegative child index.")
                body = {
                    "children": [
                        {"block_type": 2, "text": {"elements": text_elements(text)}}
                        for text in paragraphs
                    ],
                    "index": index,
                }
                method, route = "POST", route + parent + "/children"
            elif operation == "document.replace_text":
                if set(payload) != {"block_id", "text"}:
                    raise BitableError("Replace accepts block_id and text only.")
                parent = identifier(payload["block_id"])
                method, route = "PATCH", route + parent
                body = {"update_text_elements": {"elements": text_elements(payload["text"])}}
            else:
                raise BitableError("Unsupported document change.")
            snapshot_spec = {"document": token, "block": parent}
            snapshot = await self.snapshot(snapshot_spec)
            if operation == "document.insert_text":
                children = snapshot["block"].get("children", [])
                if not isinstance(children, list) or index > len(children):
                    raise BitableError(
                        "Insert index exceeds the parent block's current child count."
                    )
            elif snapshot["block"].get("block_type") != 2:
                raise BitableError("Text replacement currently supports plain text blocks only.")
            query = {
                "document_revision_id": snapshot["revision"],
                "client_token": str(uuid.uuid4()),
            }
        return {
            "operation": operation,
            "method": method,
            "route": route,
            "body": body,
            "query": query,
            "snapshot_spec": snapshot_spec,
            "snapshot": fingerprint(snapshot),
            "preconditions": {
                "document_revision": snapshot["revision"] if snapshot else None,
                "atomic_compare_and_swap": False,
                "note": "Checks revision and block before dispatch; external editors may race. "
                "Replacing text replaces its inline styles. Other blocks remain untouched.",
            },
        }

    async def check(self, prepared):
        if fingerprint(await self.snapshot(prepared["snapshot_spec"])) != prepared["snapshot"]:
            raise BitableError("Document changed after preview; prepare again.")

    async def dispatch(self, prepared):
        data = await self.api.request(
            prepared["method"], prepared["route"], params=prepared["query"], json=prepared["body"]
        )
        result = {"operation": prepared["operation"]}
        if prepared["operation"] == "document.create":
            token = data.get("document", {}).get("document_id")
            if not isinstance(token, str) or not token:
                raise BitableError("No confirmed document ID; inspect before retrying.")
            return result | {"document_id": token}
        revision = data.get("document_revision_id")
        if type(revision) is not int or revision < 1:
            raise BitableError("No confirmed document revision; inspect before retrying.")
        if prepared["operation"] == "document.insert_text":
            children = data.get("children", [])
            ids = [x.get("block_id") for x in children if isinstance(x, dict)]
            if len(ids) != len(prepared["body"]["children"]) or not all(
                isinstance(x, str) and x for x in ids
            ):
                raise BitableError("Response does not confirm every inserted block.")
            result["block_ids"] = ids
        return result | {"document_revision_id": revision}
