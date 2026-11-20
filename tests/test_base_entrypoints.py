"""Bare Base and Wiki entrypoints discover tables without guessing a write target."""

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from feishu_bitable_mcp.client import FeishuClient
from feishu_bitable_mcp.config import BitableError, Settings
from feishu_bitable_mcp.resources import Resource
from feishu_bitable_mcp.server import build_server

ROOT = "https://example.feishu.cn/base/DemoBaseToken0001"
WIKI = "https://example.feishu.cn/wiki/WikiDemoToken0001"
TABLE = "tblDemoTable01"
VIEW = "vewDemoView1"


def service(count=2, read_tables=frozenset(), ledger=None):
    seen = []

    def upstream(request):
        seen.append(request)
        path = request.url.path
        if path.endswith("/internal"):
            return httpx.Response(200, json={
                "code": 0, "tenant_access_token": "fictional-token", "expire": 7200,
            })
        if path.endswith("/records/batch_create"):
            data = {"records": [{"record_id": "recCreatedDemo1"}]}
        elif path.endswith("/get_node"):
            data = {"node": {"obj_type": "bitable", "obj_token": "DemoBaseToken0001"}}
        elif path.endswith("/tables"):
            data = {"items": [
                {"table_id": TABLE, "name": "First"},
                {"table_id": "tblDemoTable02", "name": "Second"},
            ][:count], "has_more": False}
        elif path.endswith("/fields"):
            data = {"items": [{"field_id": "fldTitle", "field_name": "Title",
                               "type": 1, "is_primary": True}], "has_more": False}
        elif path.endswith("/records"):
            data = {"items": [{"record_id": "recDemoOne", "fields": {"Title": "Example"}}],
                    "has_more": False, "total": 1}
        else:
            data = {"app": {"name": "Example Base"}}
        return httpx.Response(200, json={"code": 0, "data": data})

    changes = {} if ledger is None else {
        "enable_changes": True,
        "auth_token": "fictional-owner-token-" * 3,
        "change_policy": {"bitable.create_records": [ROOT + "?table=" + TABLE]},
        "change_ledger": str(ledger),
    }
    settings = Settings(
        "fictional-app", "fictional-secret", read_tables=read_tables, **changes,
    )
    api = FeishuClient(settings, transport=httpx.MockTransport(upstream))
    return build_server(settings, api), seen


@pytest.mark.parametrize("entry", [ROOT, WIKI])
@pytest.mark.parametrize("tool", [
    "get_bitable_info", "list_fields", "list_records", "inspect_table",
])
async def test_multiple_tables_are_listed_without_reading_arbitrary_records(entry, tool):
    server, seen = service()
    async with Client(server) as client:
        result = (await client.call_tool(tool, {"url": entry})).structured_content
    assert result["selection_required"] is True
    assert result["table_count"] == 2
    assert result["tables"][0]["url"] == ROOT + "?table=" + TABLE
    assert not any(r.url.path.endswith(("/records", "/fields")) for r in seen)
    assert all(r.method == "GET" or r.url.path.endswith("/internal") for r in seen)


async def test_single_visible_table_can_be_read_from_a_root_url():
    server, _ = service(read_tables=frozenset({("DemoBaseToken0001", TABLE)}))
    async with Client(server) as client:
        result = (await client.call_tool("inspect_table", {"url": WIKI})).structured_content
    assert result["table_id"] == TABLE
    assert result["sample_records"][0]["fields"]["Title"] == "Example"


async def test_wiki_table_and_view_are_preserved_for_record_reads():
    server, seen = service()
    async with Client(server) as client:
        result = (await client.call_tool("list_records", {
            "url": WIKI + f"?table={TABLE}&view={VIEW}",
        })).structured_content
    assert result["table_id"] == TABLE and result["view_id"] == VIEW
    requests = [r for r in seen if r.url.path.endswith("/records")]
    assert len(requests) == 1 and requests[0].url.params["view_id"] == VIEW


async def test_direct_base_can_be_discovered_and_selected_table_restrictions_hold():
    server, seen = service(read_tables=frozenset({("DemoBaseToken0001", TABLE)}))
    async with Client(server) as client:
        result = (await client.call_tool("resolve_resource", {"url": ROOT})).structured_content
        assert [t["table_id"] for t in result["tables"]] == [TABLE]
        before = len(seen)
        with pytest.raises(ToolError, match="FEISHU_READ_TABLE_URLS"):
            await client.call_tool("list_records", {"url": ROOT + "?table=tblDemoTable02"})
        assert len(seen) == before


@pytest.mark.parametrize("query", [
    "?table=invalid", f"?table={TABLE}&table={TABLE}", "?view=invalid",
    f"?view={VIEW}", f"?table={TABLE}&view={VIEW}&view={VIEW}",
])
def test_root_and_wiki_query_ids_are_strictly_validated(query):
    for entry in (ROOT, WIKI):
        with pytest.raises(BitableError):
            Resource.parse(entry + query)


async def test_write_does_not_silently_pick_the_only_table():
    from feishu_bitable_mcp.resources import ResourceClient

    server, seen = service(count=1)
    # Exercise the resolver policy independently of the optional write-tool switch.
    settings = Settings("fictional-app", "fictional-secret")
    async def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"code": 0, "data": {
            "items": [{"table_id": TABLE, "name": "Only"}], "has_more": False,
        }})
    api = FeishuClient(settings, transport=httpx.MockTransport(handler))
    api._token, api._expires = "fictional-token", float("inf")
    try:
        result = await ResourceClient(api).bitable_target(ROOT, auto_select=False)
        assert result["selection_required"] is True
    finally:
        await api.close()


async def test_wiki_write_uses_resolved_exact_allowlist_and_confirmation(tmp_path):
    server, seen = service(ledger=tmp_path / "receipts.sqlite3")
    async with Client(server) as client:
        selection = (await client.call_tool("prepare_change", {
            "operation": "bitable.create_records", "url": WIKI,
            "payload": {"records": [{"fields": {"Title": "Approved example"}}]},
            "request_id": "wiki-write-example-01",
        })).structured_content
        assert selection["selection_required"] is True and "plan_id" not in selection
        args = {
            "operation": "bitable.create_records", "url": WIKI + "?table=" + TABLE,
            "payload": {"records": [{"fields": {"Title": "Approved example"}}]},
            "request_id": "wiki-write-example-01",
        }
        preview = (await client.call_tool("prepare_change", args)).structured_content
        assert preview["target_url"] == ROOT + "?table=" + TABLE
        assert not any(r.url.path.endswith("/batch_create") for r in seen)
        confirmation = {"plan_id": preview["plan_id"],
                        "confirmation_digest": preview["confirmation_digest"]}
        with pytest.raises(ToolError, match="Confirm"):
            await client.call_tool("commit_change", confirmation)
        assert not any(r.url.path.endswith("/batch_create") for r in seen)
        result = (await client.call_tool("commit_change", {
            **confirmation, "confirm": True,
        })).structured_content
        assert result["status"] == "succeeded"
        with pytest.raises(ToolError, match="not operator-authorized"):
            await client.call_tool("prepare_change", {
                **args, "url": WIKI + "?table=tblDemoTable02",
                "request_id": "wiki-write-example-02",
            })
    writes = [r for r in seen if r.url.path.endswith("/batch_create")]
    assert len(writes) == 1
    assert TABLE in writes[0].url.path
