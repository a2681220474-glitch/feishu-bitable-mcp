"""Diagnostics must be read-only and keep business content out of terminal output."""

import json

import httpx
import pytest

from feishu_bitable_mcp.client import FeishuClient
from feishu_bitable_mcp.config import Settings
from feishu_bitable_mcp.doctor import diagnose

URL = "https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01"


@pytest.mark.parametrize("failure", [None, "auth", "fields", "records"])
async def test_diagnostic_readback_and_failure_stages(failure):
    settings = Settings("fictional-app", "fictional-secret")
    calls = []

    def respond(request):
        calls.append(request)
        path = request.url.path
        if path.endswith("/internal"):
            if failure == "auth":
                return httpx.Response(200, json={"code": 10003, "msg": "fictional-secret"})
            return httpx.Response(200, json={
                "code": 0, "tenant_access_token": "fictional-tenant", "expire": 7200,
            })
        if failure and path.endswith("/" + failure):
            return httpx.Response(403, json={"code": 99991672, "msg": "Permission denied"})
        if path.endswith("/tables"):
            data = {"items": [{"table_id": "tblDemoTable01"}], "has_more": False}
        elif path.endswith("/fields"):
            data = {"items": [{"field_name": "private-field"}], "has_more": False}
        elif path.endswith("/records"):
            data = {"items": [{"record_id": "recDemo", "fields": {"x": "private-data"}}]}
        else:
            data = {"app": {"name": "private-base"}}
        return httpx.Response(200, json={"code": 0, "data": data})

    api = FeishuClient(settings, transport=httpx.MockTransport(respond))
    try:
        offline = await diagnose(settings, None, api)
        assert offline["ok"] and not calls
        result = await diagnose(settings, URL, api)
        assert result["ok"] == (failure is None)
        assert all(r.method == "GET" or r.url.path.endswith("/internal") for r in calls)
        rendered = json.dumps(result)
        for value in ["fictional-secret", "fictional-tenant", "private-data", "private-field"]:
            assert value not in rendered
        if failure:
            assert result["checks"][-1]["ok"] is False
            assert "next_step" in result["checks"][-1]
    finally:
        await api.close()
