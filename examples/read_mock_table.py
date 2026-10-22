"""Run after mock_server.py; contacts only the localhost demo MCP server."""

import asyncio
import json

from fastmcp import Client


async def main() -> None:
    async with Client("http://127.0.0.1:8765/mcp") as client:
        result = await client.call_tool(
            "inspect_table",
            {
                "url": "https://example.feishu.cn/base/DemoBaseToken0001?table=tblDemoTable01",
            },
        )
        print(json.dumps(result.structured_content, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
