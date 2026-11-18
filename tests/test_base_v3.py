"""Granular user grants select v3; no privilege fallback or lossy matrix conversion."""

from dataclasses import replace

import httpx
import pytest
from fastmcp.server.auth import AccessToken

from feishu_bitable_mcp.client import FeishuClient
from feishu_bitable_mcp.config import BitableError, Settings, Target

TARGET = Target("DemoBaseToken0001", "tblDemoTable01", "vewDemoView01")


@pytest.fixture
async def context(monkeypatch):
    from fastmcp.server import dependencies

    current = [
        AccessToken(
            token="fictional-user",
            client_id="test",
            subject="owner-one",
            scopes=[],
            claims={"feishu_granted_scopes": ["base:record:read"]},
        )
    ]
    monkeypatch.setattr(dependencies, "get_access_token", lambda: current[0])
    seen, state = [], {"rev": 7, "invalid": False}

    def upstream(request):
        seen.append(request)
        assert request.method == "GET" and "/base/v3/" in request.url.path
        assert request.headers["authorization"] == "Bearer fictional-user"
        row = ["Example", {"nested": [1, "unchanged"]}]
        data = {
            "fields": ["Title", "Raw"],
            "field_id_list": ["fldTitle", "fldRaw"],
            "field_type_list": ["text", "custom"],
            "data": [row],
            "record_id_list": [
                "recDemoOne" if request.url.params["offset"] == "0" else "recDemoTwo"
            ],
            "has_more": request.url.params["offset"] == "0",
            "rev": state["rev"],
            "timezone": "Asia/Shanghai",
            "new_upstream_property": {"keep": True},
        }
        if state["invalid"]:
            data["data"] = [["lost-column"]]
        return httpx.Response(200, json={"code": 0, "data": data})

    settings = Settings(
        "fictional-app",
        "fictional-secret",
        identity="user",
        public_url="https://mcp.example.com/mcp",
        user_scopes=("base:record:read",),
    )
    api = FeishuClient(settings, transport=httpx.MockTransport(upstream))
    yield api, seen, state, current
    await api.close()


async def test_granular_read_pages_preserve_matrix_and_all_metadata(context):
    api, seen, _, _ = context
    first = await api.records(TARGET, 500)
    assert first["api_version"] == "base/v3" and first["effective_page_size"] == 200
    assert first["records"][0]["fields"]["Raw"] == {"nested": [1, "unchanged"]}
    assert first["data"][0][1] == first["records"][0]["fields"]["Raw"]
    assert first["new_upstream_property"] == {"keep": True} and "total" not in first
    assert first["observed_record_count"] is None
    second = await api.records(TARGET, 100, first["page_token"])
    assert seen[0].url.params["view_id"] == TARGET.view_id
    assert seen[1].url.params["offset"] == "1"
    assert second["observed_record_count"] == 2 and second["page_token"] is None


async def test_cursor_rejects_other_user_table_or_view_before_network(context):
    api, seen, _, current = context
    first = await api.records(TARGET, 2)
    for target in [replace(TARGET, table_id="tblOtherTable01"), replace(TARGET, view_id=None)]:
        with pytest.raises(BitableError, match="cursor"):
            await api.records(target, 2, first["page_token"])
    current[0] = current[0].model_copy(update={"subject": "owner-two"})
    with pytest.raises(BitableError, match="cursor"):
        await api.records(TARGET, 2, first["page_token"])
    assert len(seen) == 1


async def test_revision_change_requires_explicit_pagination_restart(context):
    api, _, state, _ = context
    first = await api.records(TARGET, 2)
    state["rev"] = 8
    with pytest.raises(BitableError, match="revision changed"):
        await api.records(TARGET, 2, first["page_token"])


async def test_matrix_missing_a_column_is_not_silently_accepted(context):
    api, _, state, _ = context
    state["invalid"] = True
    with pytest.raises(BitableError, match="invalid Base v3"):
        await api.records(TARGET, 2)


@pytest.mark.parametrize("value", ["invalid", "v3.@@@@", "v3.e30", "v3.MQ"])
async def test_bad_cursor_is_rejected_without_network(context, value):
    api, seen, _, _ = context
    with pytest.raises(BitableError, match="cursor"):
        await api.records(TARGET, 2, value)
    assert not seen


async def test_grant_change_does_not_implicitly_change_api_mid_cursor(context):
    api, seen, _, current = context
    first = await api.records(TARGET, 2)
    current[0].claims["feishu_granted_scopes"].append("bitable:app:readonly")
    await api.records(TARGET, 2, first["page_token"])
    assert len(seen) == 2
    current[0].claims["feishu_granted_scopes"] = ["bitable:app:readonly"]
    with pytest.raises(BitableError, match="grant changed"):
        await api.records(TARGET, 2, first["page_token"])
    assert len(seen) == 2
