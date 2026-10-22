"""End-to-end MCP tool calls exercise only an in-process fake Feishu API."""

import json

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from feishu_bitable_mcp.client import FeishuClient
from feishu_bitable_mcp.config import Settings, Target
from feishu_bitable_mcp.server import build_server

URL = "https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01&view=vewDemoView1"
SCHEMA = [
    {
        "field_id": "fldDemoTitle",
        "field_name": "Title",
        "type": 1,
        "is_primary": True,
        "property": {"fictional": {"preserve": True}},
    }
]


def fixture_server(write=False):
    seen = []
    settings = Settings(
        "fictional-app",
        "fictional-secret",
        auth_token="owner-test-token-" * 3,
        enable_writes=write,
        write_tables=frozenset([Target.parse(URL).key]),
    )

    def upstream(request):
        seen.append(request)
        path = request.url.path
        if path.endswith("/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "mock-api-token", "expire": 7200}
            )
        data = {}
        if path.endswith("/records") and request.method == "POST":
            data = {
                "record": {
                    "record_id": "recDemoNew",
                    "fields": json.loads(request.content)["fields"],
                }
            }
        elif path.endswith("/fields"):
            data = {"items": SCHEMA, "has_more": False}
        elif path.endswith("/tables"):
            data = {"items": [{"table_id": "tblDemoTable01", "name": "Demo"}], "has_more": False}
        elif path.endswith("/records"):
            data = {
                "items": [
                    {
                        "record_id": "recDemoOne",
                        "fields": {"Title": "Fictional sample", "Extra": [1, {"x": 2}]},
                    }
                ],
                "total": 1,
                "has_more": False,
            }
        else:
            data = {"app": {"name": "Demo Base"}}
        return httpx.Response(200, json={"code": 0, "data": data})

    api = FeishuClient(settings, transport=httpx.MockTransport(upstream))
    return build_server(settings, api), seen


async def test_read_catalog_is_minimal_and_annotations_read_only():
    server, seen = fixture_server()
    async with Client(server) as client:
        tools = await client.list_tools()
        assert {x.name for x in tools} == {
            "get_bitable_info",
            "list_fields",
            "list_records",
            "inspect_table",
        }
        for tool in tools:
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False
        assert not seen


async def test_inspect_and_paged_records_keep_all_raw_fields_and_view():
    server, seen = fixture_server()
    async with Client(server) as client:
        inspect = await client.call_tool("inspect_table", {"url": URL})
        data = inspect.structured_content
        assert data["field_count"] == 1
        assert data["table_name"] == "Demo"
        assert data["record_count"] == 1
        assert data["primary_field"]["property"] == SCHEMA[0]["property"]
        records = await client.call_tool("list_records", {"url": URL, "page_size": 5})
        assert records.structured_content["records"][0]["fields"]["Extra"] == [1, {"x": 2}]
        assert all(
            r.url.params["view_id"] == "vewDemoView1"
            for r in seen
            if r.url.path.endswith("/records")
        )
        assert not any(r.method != "GET" for r in seen if not r.url.path.endswith("/internal"))


async def test_write_requires_confirmation_then_sends_only_validated_fields():
    server, seen = fixture_server(write=True)
    async with Client(server) as client:
        tools = {x.name: x for x in await client.list_tools()}
        assert tools["create_record"].annotations.read_only_hint is False
        assert tools["create_record"].annotations.destructive_hint is False
        assert tools["create_record"].annotations.idempotent_hint is False
        with pytest.raises(ToolError, match="Confirm"):
            await client.call_tool("create_record", {"url": URL, "fields": {"Title": "Demo"}})
        assert not seen
        with pytest.raises(ToolError, match="Unknown field"):
            await client.call_tool(
                "create_record", {"url": URL, "fields": {"Unknown": "Demo"}, "confirm": True}
            )
        assert not any(r.method == "POST" and r.url.path.endswith("/records") for r in seen)
        result = await client.call_tool(
            "create_record", {"url": URL, "fields": {"Title": "Demo"}, "confirm": True}
        )
        assert result.structured_content["record"]["record_id"] == "recDemoNew"
        writes = [r for r in seen if r.method == "POST" and r.url.path.endswith("/records")]
        assert len(writes) == 1
        assert json.loads(writes[0].content) == {"fields": {"Title": "Demo"}}


async def test_invalid_url_and_non_allowlisted_write_do_not_touch_upstream():
    server, seen = fixture_server(write=True)
    async with Client(server) as client:
        for url in [
            "https://evil.example/base/DemoBaseToken0001?table=tblDemoTable01",
            URL.replace("tblDemoTable01", "tblOtherTable01"),
        ]:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "create_record", {"url": url, "fields": {"Title": "Demo"}, "confirm": True}
                )
        assert not seen


async def test_http_initialization_lists_and_calls_actual_read_tools():
    server, seen = fixture_server()
    app = server.http_app(path="/mcp", stateless_http=True, json_response=True)
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + "owner-test-token-" * 3,
    }
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://localhost", headers=headers
        ) as client:
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "mock-client", "version": "1"},
                    },
                },
            )
            assert response.status_code == 200
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "inspect_table", "arguments": {"url": URL}},
                },
            )
            assert response.status_code == 200
            result = response.json()["result"]
            assert result["isError"] is False
            assert result["structuredContent"]["table_name"] == "Demo"
            assert seen
