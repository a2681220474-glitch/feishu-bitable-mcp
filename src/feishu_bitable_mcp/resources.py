"""Strict URL routing and read-only document, spreadsheet and Drive operations."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlsplit

import httpx

from .client import FeishuClient
from .config import BitableError, Target

MAX_DOWNLOAD = 20 * 1024 * 1024


@dataclass(frozen=True)
class Resource:
    kind: str
    token: str
    sheet_id: str | None = None
    table_id: str | None = None
    view_id: str | None = None

    @classmethod
    def parse(cls, url: str):
        if not isinstance(url, str) or len(url) > 4096 or any(ord(c) <= 32 for c in url):
            raise BitableError("Use a complete HTTPS Feishu resource URL.")
        try:
            parts = urlsplit(url)
            query = parse_qs(parts.query, keep_blank_values=True, max_num_fields=30)
            match = re.fullmatch(
                r"/(base|docx|sheets|wiki|file|drive/file)/([A-Za-z0-9]{10,100})/?", parts.path
            )
            valid = (
                parts.scheme == "https" and match is not None
                and re.fullmatch(
                    r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)*feishu\.cn",
                    parts.hostname or "",
                )
                and parts.username is None and parts.password is None and parts.port is None
                and not parts.fragment and "\\" not in url and "\x7f" not in url
            )
        except ValueError:
            valid = False
        if not valid or match is None:
            raise BitableError(
                "Accept HTTPS Feishu /base/, /docx/, /sheets/, /wiki/ or /file/ links."
            )
        sheets = query.get("sheet", [])
        if sheets and (len(sheets) != 1 or not re.fullmatch(r"[A-Za-z0-9]{1,100}", sheets[0])):
            raise BitableError("URL contains an invalid or duplicate sheet parameter.")
        def identifier(name, pattern):
            values = query.get(name, [])
            if values and (len(values) != 1 or not re.fullmatch(pattern, values[0])):
                raise BitableError(f"URL contains an invalid or duplicate {name} parameter.")
            return values[0] if values else None

        table_id = identifier("table", r"tbl[A-Za-z0-9]{7,100}")
        view_id = identifier("view", r"vew[A-Za-z0-9]{7,100}")
        if (table_id or view_id) and match[1] not in {"base", "wiki"}:
            raise BitableError("table/view parameters require a Base or Wiki Base URL.")
        if view_id and not table_id:
            raise BitableError("A view parameter requires an explicit table parameter.")
        kind = {"drive/file": "file", "base": "bitable"}.get(match[1], match[1])
        return cls(kind, match[2], sheets[0] if sheets else None, table_id, view_id)


class ResourceClient:
    def __init__(self, api: FeishuClient):
        self.api = api

    async def resolve(self, url: str) -> Resource:
        resource = Resource.parse(url)
        allowed = self.api.settings.resource_urls
        if allowed and (resource.kind, resource.token) not in {
            (item.kind, item.token) for item in map(Resource.parse, allowed)
        }:
            raise BitableError("This resource is not in FEISHU_READ_RESOURCE_URLS.")
        if resource.kind == "wiki":
            data = await self.api.request(
                "GET", "/wiki/v2/spaces/get_node", params={"token": resource.token}
            )
            node = data.get("node", {})
            token, kind = node.get("obj_token"), node.get("obj_type")
            if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9]{10,100}", token):
                raise BitableError("Wiki returned an invalid underlying resource.")
            kind = {"sheet": "sheets"}.get(kind, kind)
            if kind not in {"docx", "sheets", "file", "bitable"}:
                raise BitableError("This Wiki resource type is not supported.")
            if (resource.table_id or resource.view_id) and kind != "bitable":
                raise BitableError("table/view parameters require a Wiki pointing to a Base.")
            resource = Resource(
                kind, token, resource.sheet_id, resource.table_id, resource.view_id,
            )
        return resource

    async def describe(self, url: str):
        resource = await self.resolve(url)
        return await self._describe(url, resource)

    async def _describe(self, url: str, resource: Resource):
        route_kind = "base" if resource.kind == "bitable" else resource.kind
        direct = f"https://{urlsplit(url).hostname}/{route_kind}/{resource.token}"
        if resource.kind == "sheets" and resource.sheet_id:
            direct += "?sheet=" + resource.sheet_id
        result = {
            "kind": resource.kind, "token": resource.token, "sheet_id": resource.sheet_id,
            "resource_url": direct,
        }
        if resource.kind == "bitable":
            allowed = self.api.settings.read_tables
            if allowed and not any(app == resource.token for app, _ in allowed):
                raise BitableError("This Base is outside FEISHU_READ_TABLE_URLS.")
            tables = await self.api.all_items(f"/bitable/v1/apps/{resource.token}/tables")
            visible = []
            for table in tables:
                table_id = table.get("table_id")
                if not isinstance(table_id, str) or not re.fullmatch(
                    r"tbl[A-Za-z0-9]{7,100}", table_id
                ):
                    raise BitableError("Feishu returned an invalid table ID.")
                if not allowed or (resource.token, table_id) in allowed:
                    visible.append({**table, "url": direct + "?table=" + table_id})
            result["tables"] = visible
            result["table_count"] = len(visible)
            if resource.table_id:
                selected = Target(resource.token, resource.table_id, resource.view_id)
                self.api.settings.authorize(selected)
                result.update(selected.identifiers())
                result["resource_url"] = direct + "?table=" + resource.table_id
                if resource.view_id:
                    result["resource_url"] += "&view=" + resource.view_id
        return result

    async def bitable_target(self, url: str, *, auto_select: bool = True):
        """Discover tables for a Base root; never silently choose among multiple tables."""
        resource = await self.resolve(url)
        if resource.kind != "bitable":
            raise BitableError("This read tool requires a Base or Wiki pointing to a Base.")
        if resource.table_id:
            target = Target(resource.token, resource.table_id, resource.view_id)
            self.api.settings.authorize(target)
            return target
        discovery = await self._describe(url, resource)
        tables = discovery["tables"]
        if auto_select and len(tables) == 1:
            return Target(resource.token, tables[0]["table_id"])
        return {
            **discovery,
            "selection_required": True,
            "message": "Choose the intended table from tables and reuse its URL. "
            "No records have been read or modified.",
        }

    async def document(self, url: str, page_size: int, page_token: str | None):
        resource = await self.resolve(url)
        if resource.kind != "docx":
            raise BitableError("Use a Feishu docx document or Wiki link pointing to a docx.")
        route = f"/docx/v1/documents/{resource.token}"
        metadata = await self.api.request("GET", route)
        params = {"page_size": page_size, "document_revision_id": -1}
        if page_token:
            params["page_token"] = page_token
        data = await self.api.request("GET", route + "/blocks", params=params)
        if not isinstance(data.get("items"), list):
            raise BitableError("Feishu returned invalid document blocks.")
        if data.get("has_more") and (
            not isinstance(data.get("page_token"), str)
            or not data["page_token"] or data["page_token"] == page_token
        ):
            raise BitableError("Document pagination did not advance.")
        return {"document": metadata, **data}

    async def spreadsheet(self, url: str):
        resource = await self.resolve(url)
        if resource.kind != "sheets":
            raise BitableError("Use a Feishu Sheets URL or Wiki link pointing to a spreadsheet.")
        route = f"/sheets/v3/spreadsheets/{resource.token}"
        info = await self.api.request("GET", route)
        sheets = await self.api.request("GET", route + "/sheets/query")
        return {"spreadsheet": info, "worksheets": sheets}

    async def cells(self, url: str, sheet_id: str | None, area: str, render: str):
        resource = await self.resolve(url)
        if resource.kind != "sheets":
            raise BitableError("Use a Feishu Sheets URL.")
        sheet_id = sheet_id or resource.sheet_id
        if not sheet_id or not re.fullmatch(r"[A-Za-z0-9]{1,100}", sheet_id):
            raise BitableError("Choose sheet_id from get_spreadsheet_info or the URL sheet=.")
        match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6}):([A-Z]{1,3})([1-9][0-9]{0,6})", area)
        if not match:
            raise BitableError("range must be an explicit rectangle such as A1:T100.")

        def column(name):
            result = 0
            for char in name:
                result = result * 26 + ord(char) - 64
            return result

        width = column(match[3]) - column(match[1]) + 1
        height = int(match[4]) - int(match[2]) + 1
        if width < 1 or height < 1 or width * height > 5000:
            raise BitableError("Choose a forward rectangle of at most 5000 cells; read in windows.")
        qualified = f"{sheet_id}!{area}"
        data = await self.api.request(
            "GET", f"/sheets/v2/spreadsheets/{resource.token}/values/{quote(qualified, safe='')}",
            params={"valueRenderOption": render, "dateTimeRenderOption": "FormattedString"},
        )
        return {"requested_range": qualified, "render_option": render, **data}

    async def download_excel(self, url: str) -> bytes:
        resource = await self.resolve(url)
        if resource.kind != "file":
            raise BitableError("Use a Drive .xlsx file URL; online Sheets use read_spreadsheet.")
        token = await self.api.token()
        try:
            async with asyncio.timeout(25), self.api._requests:
                async with self.api._http.stream(
                    "GET", f"/drive/v1/files/{resource.token}/download",
                    headers={"Authorization": f"Bearer {token}"},
                ) as response:
                    if (
                        not response.is_success
                        or "json" in response.headers.get("content-type", "")
                    ):
                        await response.aread()
                        payload = self.api._payload(response, "Excel download failed")
                        self.api._raise_api(
                            response, payload, "Excel download failed", request_tokens=(token,)
                        )
                        raise BitableError("Feishu did not return an Excel file.")
                    content = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        content.extend(chunk)
                        if len(content) > MAX_DOWNLOAD:
                            raise BitableError("Excel exceeds the 20 MiB download limit.")
                    return bytes(content)
        except (httpx.HTTPError, TimeoutError):
            raise BitableError("Excel download failed or timed out; try again later.") from None
