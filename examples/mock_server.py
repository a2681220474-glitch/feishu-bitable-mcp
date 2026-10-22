"""Offline demo: serve fictional read-only data on port 8765 without Feishu credentials."""

import httpx

from feishu_bitable_mcp.client import FeishuClient
from feishu_bitable_mcp.config import Settings
from feishu_bitable_mcp.server import build_server


def respond(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/internal"):
        return httpx.Response(
            200,
            json={
                "code": 0,
                "tenant_access_token": "fictional-demo-token",
                "expire": 7200,
            },
        )
    if path.endswith("/fields"):
        data = {
            "items": [
                {
                    "field_id": "fldDemoTitle",
                    "field_name": "Title",
                    "type": 1,
                    "is_primary": True,
                    "property": {},
                }
            ],
            "has_more": False,
        }
    elif path.endswith("/records"):
        data = {
            "items": [
                {
                    "record_id": "recDemoOne",
                    "fields": {"Title": "Fictional demo record"},
                }
            ],
            "total": 1,
            "has_more": False,
        }
    elif path.endswith("/tables"):
        data = {
            "items": [{"table_id": "tblDemoTable01", "name": "Fictional demo"}],
            "has_more": False,
        }
    else:
        data = {"app": {"name": "Fictional Base"}}
    return httpx.Response(200, json={"code": 0, "data": data})


if __name__ == "__main__":
    settings = Settings("fictional-demo-app", "fictional-demo-secret")
    api = FeishuClient(settings, transport=httpx.MockTransport(respond))
    build_server(settings, api).run(
        transport="http",
        host="127.0.0.1",
        port=8765,
        path="/mcp",
        show_banner=False,
    )
