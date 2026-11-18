"""Wiki discovery returns usable direct URLs without widening read policy."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from feishu_bitable_mcp.config import BitableError, Settings
from feishu_bitable_mcp.resources import ResourceClient

WIKI = "https://example.feishu.cn/wiki/DemoWikiToken0001"


def api(kind="bitable", allowed=frozenset()):
    settings = Settings(
        "fictional-app", "fictional-secret", resource_urls=(WIKI,), read_tables=allowed
    )
    return SimpleNamespace(
        settings=settings,
        request=AsyncMock(
            return_value={"node": {"obj_type": kind, "obj_token": "DemoObjectToken01"}}
        ),
        all_items=AsyncMock(
            return_value=[
                {"table_id": "tblAllowedTable01", "name": "Allowed"},
                {"table_id": "tblOtherTable01", "name": "Do not expose"},
            ]
        ),
    )


async def test_wiki_base_provides_usable_table_urls():
    source = api()
    value = await ResourceClient(source).describe(WIKI)
    assert value["resource_url"] == "https://example.feishu.cn/base/DemoObjectToken01"
    assert len(value["tables"]) == 2
    assert value["tables"][0]["url"].endswith("?table=tblAllowedTable01")


async def test_wiki_base_listing_obeys_exact_read_table_policy():
    source = api(allowed=frozenset({("DemoObjectToken01", "tblAllowedTable01")}))
    value = await ResourceClient(source).describe(WIKI)
    assert [x["name"] for x in value["tables"]] == ["Allowed"]
    source.settings = replace(
        source.settings, read_tables=frozenset({("OtherBaseToken01", "tblAllowedTable01")})
    )
    source.all_items.reset_mock()
    with pytest.raises(BitableError, match="outside"):
        await ResourceClient(source).describe(WIKI)
    source.all_items.assert_not_called()


@pytest.mark.parametrize("kind,path", [("docx", "docx"), ("sheet", "sheets"), ("file", "file")])
async def test_wiki_direct_urls_for_subsequent_tools(kind, path):
    source = api(kind)
    value = await ResourceClient(source).describe(WIKI + "?sheet=sheetA1")
    suffix = "?sheet=sheetA1" if kind == "sheet" else ""
    assert value["resource_url"] == f"https://example.feishu.cn/{path}/DemoObjectToken01{suffix}"
    source.all_items.assert_not_called()
