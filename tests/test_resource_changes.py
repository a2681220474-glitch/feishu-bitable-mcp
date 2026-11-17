"""Transport-level mutation contracts using fictional resources only."""

import json
from dataclasses import replace

import httpx
import pytest

from feishu_bitable_mcp.change_adapters import ChangeAdapters
from feishu_bitable_mcp.change_policy import OPERATIONS, authorize, target_key
from feishu_bitable_mcp.change_store import ChangeStore
from feishu_bitable_mcp.changes import ChangeEngine
from feishu_bitable_mcp.client import FeishuClient
from feishu_bitable_mcp.config import BitableError, Settings
from feishu_bitable_mcp.sheet_changes import basic_style, rectangle, values_matrix

HOST = "https://example.feishu.cn"
FOLDER = HOST + "/drive/folder/DemoFolderToken01"
DOC = HOST + "/docx/DocxDemoToken0001"
SHEET = HOST + "/sheets/SheetDemoToken01?sheet=demo01"
BOOK = SHEET.split("?")[0]
BASE = HOST + "/base/DemoBaseToken0001"
TABLE = BASE + "?table=tblDemoTable01"

CASES = [
    ("document.create", FOLDER, {"title": "Fictional doc"}, "POST", "/docx/v1/documents"),
    (
        "document.insert_text",
        DOC,
        {"paragraphs": ["Fictional", "second"], "index": 0},
        "POST",
        "/docx/v1/documents/DocxDemoToken0001/blocks/DocxDemoToken0001/children",
    ),
    (
        "document.replace_text",
        DOC,
        {"block_id": "BlockDemoToken01", "text": "New text"},
        "PATCH",
        "/docx/v1/documents/DocxDemoToken0001/blocks/BlockDemoToken01",
    ),
    (
        "sheets.create",
        FOLDER,
        {"title": "Fictional spreadsheet"},
        "POST",
        "/sheets/v3/spreadsheets",
    ),
    (
        "sheets.add_worksheet",
        BOOK,
        {"title": "Test"},
        "POST",
        "/sheets/v2/spreadsheets/SheetDemoToken01/sheets_batch_update",
    ),
    (
        "sheets.write_cells",
        SHEET,
        {"range": "A1:B1", "values": [[1, {"type": "formula", "text": "=A1*2"}]]},
        "PUT",
        "/sheets/v2/spreadsheets/SheetDemoToken01/values",
    ),
    (
        "sheets.append_cells",
        SHEET,
        {"range": "A1:B2", "values": [["new", 2]]},
        "POST",
        "/sheets/v2/spreadsheets/SheetDemoToken01/values_append",
    ),
    (
        "sheets.format_cells",
        SHEET,
        {"range": "A1:B1", "style": {"font": {"bold": True}}},
        "PUT",
        "/sheets/v2/spreadsheets/SheetDemoToken01/style",
    ),
    ("bitable.create_base", FOLDER, {"name": "Fictional Base"}, "POST", "/bitable/v1/apps"),
    (
        "bitable.create_table",
        BASE,
        {"name": "Test", "fields": [{"field_name": "Title", "type": 1}]},
        "POST",
        "/bitable/v1/apps/DemoBaseToken0001/tables",
    ),
    (
        "bitable.create_field",
        TABLE,
        {"field_name": "Tag", "type": 3, "property": {"options": [{"name": "New"}]}},
        "POST",
        "/bitable/v1/apps/DemoBaseToken0001/tables/tblDemoTable01/fields",
    ),
    (
        "bitable.update_records",
        TABLE,
        {"records": [{"record_id": "recDemoRecord01", "fields": {"Title": "After"}}]},
        "POST",
        "/bitable/v1/apps/DemoBaseToken0001/tables/tblDemoTable01/records/batch_update",
    ),
]


@pytest.fixture
async def api_context(tmp_path):
    state = {"writes": [], "revision": 1, "cells": [["Before", 2]]}

    def reply(request):
        path = request.url.path
        if path.endswith("/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "fictional", "expire": 3600}
            )
        if request.method == "GET":
            if path.endswith("/fields"):
                data = {"items": [{"field_name": "Title", "type": 1}], "has_more": False}
            elif "/records/" in path:
                data = {"record": {"record_id": "recDemoRecord01", "fields": {"Title": "Before"}}}
            elif "/blocks/" in path:
                data = {"block": {"block_type": 2, "children": ["BlockDemoToken01"]}}
            elif path.endswith("/sheets/query"):
                data = {"sheets": [{"sheet_id": "demo01", "title": "Test"}]}
            elif "/values/" in path:
                data = {"valueRange": {"values": state["cells"]}}
            else:
                data = {"document": {"revision_id": state["revision"]}}
        else:
            body = json.loads(request.content)
            state["writes"].append((request, body))
            if path == "/open-apis/docx/v1/documents":
                data = {"document": {"document_id": "CreatedDocument01"}}
            elif "/docx/" in path:
                assert request.url.params["document_revision_id"] == "1"
                assert len(request.url.params["client_token"]) == 36
                data = {
                    "document_revision_id": 2,
                    "children": [
                        {"block_id": f"CreatedBlock000{i}"}
                        for i in range(len(body.get("children", [])))
                    ],
                }
            elif path.endswith("/sheets_batch_update"):
                assert set(body["requests"][0]) == {"addSheet"}
                data = {"replies": [{"addSheet": {"properties": {"sheetId": "new01"}}}]}
            elif path == "/open-apis/sheets/v3/spreadsheets":
                data = {"spreadsheet": {"spreadsheet_token": "CreatedSpreadsheet01"}}
            elif "/sheets/" in path:
                if path.endswith("/style"):
                    data = {"updates": {"revision": 2, "updatedRange": "demo01!A1:B1"}}
                else:
                    updates = {"updatedRange": "demo01!A1:B1", "updatedCells": 2, "revision": 2}
                    if path.endswith("/values_append"):
                        assert request.url.params["insertDataOption"] == "INSERT_ROWS"
                        data = {"updates": updates}
                    else:
                        data = updates
            elif path.endswith("/batch_update"):
                data = {"records": [{"record_id": "recDemoRecord01"}]}
            elif path.endswith("/fields"):
                data = {"field": {"field_id": "fldCreatedField01"}}
            elif path.endswith("/tables"):
                data = {"table_id": "tblCreatedTable01"}
            else:
                data = {"app": {"app_token": "CreatedBaseToken01"}}
        return httpx.Response(200, json={"code": 0, "data": data})

    settings = Settings("fictional-app", "fictional-secret", auth_token="x" * 40)
    api = FeishuClient(settings, transport=httpx.MockTransport(reply))
    yield api, state, tmp_path
    await api.close()


@pytest.mark.parametrize("operation,url,payload,method,route", CASES)
async def test_named_contracts_preview_confirm_exactly_once(
    api_context, operation, url, payload, method, route
):
    api, state, path = api_context
    settings = replace(api.settings, enable_changes=True, change_policy={operation: [url]})
    engine = ChangeEngine(settings, ChangeAdapters(api), ChangeStore(str(path / "receipts.db")))
    preview = await engine.prepare(operation, url, payload, "request-example-01")
    assert not state["writes"]
    result = await engine.commit(preview["plan_id"], preview["confirmation_digest"], True)
    assert result["status"] == "succeeded"
    request, body = state["writes"][0]
    assert request.method == method and request.url.path == "/open-apis" + route
    assert preview["exact_content"] == payload
    await engine.commit(preview["plan_id"], preview["confirmation_digest"], True)
    assert len(state["writes"]) == 1


@pytest.mark.parametrize(
    "operation,url,payload",
    [
        ("document.insert_text", DOC, {"paragraphs": ["Text"], "index": 2}),
        ("document.replace_text", DOC, {"block_id": "../../escape", "text": "New"}),
        ("sheets.write_cells", SHEET, {"sheet_id": "other01", "range": "A1:A1", "values": [[1]]}),
        ("sheets.write_cells", SHEET, {"range": "A1:B1", "values": [[1]]}),
        ("sheets.add_worksheet", BOOK, {"title": "Test", "deleteSheet": {"sheetId": "demo01"}}),
        ("bitable.create_field", TABLE, {"field_name": "Title", "type": 1}),
        (
            "bitable.create_table",
            BASE,
            {"name": "Test", "fields": [{"field_name": "Primary", "type": 3}]},
        ),
    ],
)
async def test_invalid_mutations_never_dispatch(api_context, operation, url, payload):
    api, state, _ = api_context
    with pytest.raises(BitableError):
        await ChangeAdapters(api).prepare(operation, url, payload, "request-example-01")
    assert not state["writes"]


@pytest.mark.parametrize(
    "operation,url,payload",
    [
        ("document.insert_text", DOC, {"paragraphs": ["Text"]}),
        ("sheets.write_cells", SHEET, {"range": "A1:B1", "values": [[1, 2]]}),
    ],
)
async def test_resource_conflict_prevents_dispatch(api_context, operation, url, payload):
    api, state, path = api_context
    settings = replace(api.settings, enable_changes=True, change_policy={operation: [url]})
    engine = ChangeEngine(settings, ChangeAdapters(api), ChangeStore(str(path / "receipts.db")))
    preview = await engine.prepare(operation, url, payload, "request-example-01")
    state["revision"] += 1
    state["cells"] = [["Someone changed", 3]]
    with pytest.raises(BitableError, match="changed after preview"):
        await engine.commit(preview["plan_id"], preview["confirmation_digest"], True)
    assert not state["writes"]


@pytest.mark.parametrize(
    "value",
    [
        [[float("inf")]],
        [[{"type": "formula", "text": "bad"}]],
        [["=1+2"]],
        [[1], [2, 3]],
        [[{"raw_api": "bad"}]],
    ],
)
def test_cell_contract_rejects_ambiguous_values(value):
    with pytest.raises(BitableError):
        values_matrix(value)


@pytest.mark.parametrize(
    "style",
    [
        {"delete": True},
        {"font": {"fontSize": True}},
        {"backColor": "javascript:bad"},
        {"hAlign": True},
    ],
)
def test_basic_format_rejects_unknown_options(style):
    with pytest.raises(BitableError):
        basic_style(style)


@pytest.mark.parametrize("area", ["A0:B1", "A1:ZZZ9999", "B2:A1", "A1", "demo!A1:B2"])
def test_bounded_rectangle(area):
    with pytest.raises(BitableError):
        rectangle(area)


def test_policy_has_no_deletion_or_raw_routes():
    assert not any("delete" in op or "raw" in op for op in OPERATIONS)
    assert target_key(SHEET, "sheets")[-1] == "demo01"
    with pytest.raises(BitableError):
        authorize({"sheets.write_cells": [SHEET]}, "sheets.write_cells", BOOK)
    with pytest.raises(BitableError):
        target_key(DOC.replace("example.feishu.cn", "feishu.cn.evil.example"), "docx")


async def test_mcp_preview_commit_and_status_roundtrip(api_context):
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    from feishu_bitable_mcp.server import build_server

    api, state, path = api_context
    settings = replace(
        api.settings,
        enable_changes=True,
        change_policy={"document.create": [FOLDER]},
        change_ledger=str(path / "receipts.db"),
    )
    async with Client(build_server(settings, api)) as client:
        tools = {t.name: t for t in await client.list_tools()}
        assert "create_record" not in tools and len(tools) == 12
        assert tools["prepare_change"].annotations.read_only_hint is True
        assert tools["commit_change"].annotations.destructive_hint is True
        assert tools["commit_change"].annotations.idempotent_hint is True
        assert tools["prepare_change"].input_schema["properties"]["operation"]["enum"] == list(
            OPERATIONS
        )
        result = await client.call_tool(
            "prepare_change",
            {
                "operation": "document.create",
                "url": FOLDER,
                "payload": {"title": "Fictional"},
                "request_id": "mcp-example-01",
            },
        )
        plan = result.structured_content
        arguments = {"plan_id": plan["plan_id"], "confirmation_digest": plan["confirmation_digest"]}
        with pytest.raises(ToolError):
            await client.call_tool("commit_change", arguments | {"confirm": "true"})
        assert not state["writes"]
        result = await client.call_tool("commit_change", arguments | {"confirm": True})
        assert result.structured_content["status"] == "succeeded"
        result = await client.call_tool("get_change_status", {"request_id": "mcp-example-01"})
        assert result.structured_content["receipt"]["document_id"] == "CreatedDocument01"
        assert len(state["writes"]) == 1


async def test_preview_return_value_cannot_mutate_the_dispatched_payload(api_context):
    api, state, path = api_context
    settings = replace(
        api.settings, enable_changes=True, change_policy={"sheets.write_cells": [SHEET]}
    )
    engine = ChangeEngine(settings, ChangeAdapters(api), ChangeStore(str(path / "receipts.db")))
    payload = {"range": "A1:B1", "values": [[1, 2]]}
    plan = await engine.prepare("sheets.write_cells", SHEET, payload, "content-binding-01")
    payload["values"][0][0] = 99
    plan["exact_content"]["values"][0][0] = 100
    await engine.commit(plan["plan_id"], plan["confirmation_digest"], True)
    assert state["writes"][0][1]["valueRange"]["values"] == [[1, 2]]
