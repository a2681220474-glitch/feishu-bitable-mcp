"""Read APIs preserve raw payloads; downloaded workbooks contain fictional data."""

from io import BytesIO
from zipfile import ZipFile

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from openpyxl import Workbook

from feishu_bitable_mcp.client import FeishuClient
from feishu_bitable_mcp.config import BitableError, Settings
from feishu_bitable_mcp.excel import read_excel
from feishu_bitable_mcp.resources import Resource
from feishu_bitable_mcp.server import build_server

DOC = "https://example.feishu.cn/docx/DocxDemoToken0001"
SHEET = "https://example.feishu.cn/sheets/SheetDemoToken0001?sheet=sheetA1"
FILE = "https://example.feishu.cn/file/FileDemoToken0001"
WIKI = "https://example.feishu.cn/wiki/WikiDemoToken0001"


def workbook():
    book = Workbook()
    book.active.title = "Demo"
    book.active.append(["001234567890123456789", "Title", "Formula"])
    book.active.append([42, True, "=A2*2"])
    book.create_sheet("Other")
    result = BytesIO()
    book.save(result)
    book.close()
    return result.getvalue()


@pytest.mark.parametrize("url", [
    DOC.replace("https:", "http:"), DOC + "#secret", DOC.replace("example.feishu.cn", "evil.test"),
    DOC.replace("/docx/", "/docx/../docx/"), DOC + "\n", DOC + "?x=" + "x" * 4096,
    DOC.replace("example.feishu.cn", "example.feishu.cn@evil.test"),
    DOC.replace("example.feishu.cn", "example.feishu.cn:443"),
    SHEET + "&sheet=duplicate", "/Users/example/private.xlsx",
])
def test_resource_rejects_unsafe_urls(url):
    with pytest.raises(BitableError):
        Resource.parse(url)


@pytest.mark.parametrize("kind,url", [("docx", DOC), ("sheets", SHEET), ("file", FILE)])
def test_resource_routes(kind, url):
    assert Resource.parse(url).kind == kind


async def test_all_new_read_tools_with_raw_payloads_and_pagination():
    seen = []

    def handler(request):
        seen.append(request)
        path = request.url.path
        if path.endswith("/internal"):
            return httpx.Response(200, json={
                "code": 0, "tenant_access_token": "fictional-token", "expire": 7200,
            })
        if path.endswith("/download"):
            return httpx.Response(200, content=workbook())
        if path.endswith("/get_node"):
            data = {"node": {"obj_type": "docx", "obj_token": "DocxDemoToken0001"}}
        elif path.endswith("/blocks"):
            second = request.url.params.get("page_token") == "next-page"
            data = {
                "items": [{"block_id": "b2" if second else "b1", "text": {
                    "elements": [{"text_run": {"content": "Fictional", "text_element_style": {
                        "bold": True,
                    }}}],
                }, "children": ["b2"]}],
                "has_more": not second, "page_token": None if second else "next-page",
            }
        elif "/values/" in path:
            assert request.url.params["valueRenderOption"] == "Formula"
            data = {"valueRange": {"range": "sheetA1!A1:C2", "values": [["=A2*2"]]}}
        elif path.endswith("/sheets/query"):
            data = {"sheets": [{"sheet_id": "sheetA1", "title": "Demo", "grid_properties": {}}]}
        else:
            data = {"document": {"title": "Fictional document"}}
        return httpx.Response(200, json={"code": 0, "data": data})

    api = FeishuClient(Settings("fictional-app", "fictional-secret"),
                       transport=httpx.MockTransport(handler))
    async with Client(build_server(api.settings, api)) as client:
        resolved = (await client.call_tool("resolve_resource", {"url": WIKI})).structured_content
        assert resolved["kind"] == "docx"
        page = (await client.call_tool("read_document", {"url": DOC})).structured_content
        assert page["has_more"] and page["items"][0]["text"]["elements"][0]["text_run"][
            "text_element_style"]["bold"]
        last = (await client.call_tool("read_document", {
            "url": DOC, "page_token": page["page_token"],
        })).structured_content
        assert not last["has_more"] and last["items"][0]["block_id"] == "b2"
        info = (await client.call_tool("get_spreadsheet_info", {"url": SHEET})).structured_content
        assert info["worksheets"]["sheets"][0]["sheet_id"] == "sheetA1"
        cells = (await client.call_tool("read_spreadsheet", {
            "url": SHEET, "range": "A1:C2", "render": "Formula",
        })).structured_content
        assert cells["valueRange"]["values"] == [["=A2*2"]]
        excel = (await client.call_tool("read_excel_file", {
            "url": FILE, "rows": 1, "columns": 3,
        })).structured_content
        assert excel["rows"][0][0]["value"] == "001234567890123456789"
        assert excel["has_more"] and excel["next_row"] == 2
        with pytest.raises(ToolError, match="5000"):
            await client.call_tool("read_excel_file", {"url": FILE, "rows": 1000, "columns": 100})
    assert all(r.method == "GET" or r.url.path.endswith("/internal") for r in seen)


def test_excel_formula_preservation_and_cached_value_semantics():
    result = read_excel(workbook(), "Demo", 2, 1, 1, 3, False)
    assert result["rows"][0][2]["value"] == "=A2*2"
    assert result["rows"][0][2]["data_type"] == "f"
    assert result["worksheets"] == ["Demo", "Other"]
    cached = read_excel(workbook(), "Demo", 2, 1, 1, 3, True)
    assert cached["rows"][0][2]["value"] is None


@pytest.mark.parametrize("payload", [b"not Excel", b"", b"PK\x03\x04corrupted"])
def test_invalid_excel_is_a_clear_error(payload):
    with pytest.raises(BitableError):
        read_excel(payload, None, 1, 10, 1, 5, False)


def test_excel_xml_entities_are_rejected():
    source = BytesIO(workbook())
    result = BytesIO()
    with ZipFile(source) as incoming, ZipFile(result, "w") as outgoing:
        for name in incoming.namelist():
            content = incoming.read(name)
            if name == "xl/workbook.xml":
                content = b'<!DOCTYPE workbook [<!ENTITY test "fictional">]>' + content
            outgoing.writestr(name, content)
    with pytest.raises(BitableError):
        read_excel(result.getvalue(), None, 1, 10, 1, 5, False)
