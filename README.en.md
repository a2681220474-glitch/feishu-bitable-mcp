# Feishu Bitable MCP

**English** | [简体中文](README.md) | [日本語](README.ja.md)

A lightweight, self-hosted Python MCP server that lets compatible AI clients inspect Feishu Bitable schemas and read records directly from a table URL—without manually exporting a spreadsheet or reimplementing Feishu OpenAPI calls.

> **Regional support:** Version v0.1.0 supports **Feishu (China)** only. **Lark (international)** is a related product with a different API host and separate app credentials; this release **does not** support Lark domains or applications. International Lark support would require a dedicated implementation and testing, not just a rename.
>
> This is an independent community project, not an official product of Feishu, Lark, or OpenAI.

## Why this project exists

The original workflow was simple: give ChatGPT a Feishu Bitable link, let an authorized MCP integration read its structure and records, and analyze the data without exporting files first. The early private prototype successfully read a real Bitable table through ChatGPT and created one record in a fixed test table. This newly open-sourced implementation has been independently rewritten and tested using fictional data and mocked APIs; **live Feishu/ChatGPT integration has not yet been re-verified for v0.1.0**.

## MCP tools
## Practical goal and implementation status

**Original motivation:** Give ChatGPT a Feishu Bitable URL so an authorized MCP connection can inspect the table and read records for analysis, without repeatedly exporting spreadsheets or hand-writing Feishu API calls. This describes the intended workflow; ChatGPT web end-to-end compatibility has **not** been re-verified for v0.1.0.

- **Available now (Feishu China):** Base metadata, field schemas, paginated record reads, table inspection, and an optional authenticated, allowlisted, field-validated single-record creation tool.
- **Not implemented:** Editing existing records, creating tables, or editing ordinary Feishu cloud documents.
- **Not supported:** Lark international tenants, domains, and app credentials. Their API environment requires separate implementation and validation.

The new public release is validated with fictional data and mock API tests. The earlier **private prototype**, not v0.1.0, was tested against a real Feishu test table through ChatGPT.


| Tool | What it does |
| --- | --- |
| `get_bitable_info(url)` | Parses a Feishu Bitable URL and returns Base/table details. |
| `list_fields(url)` | Reads paginated schema fields and preserves original metadata. |
| `list_records(url, page_size, page_token)` | Reads one page of records and returns the next pagination token. |
| `inspect_table(url, sample_size)` | Inspects the schema and a small set of original records. |
| `create_record(url, fields, confirm)` | **Optional and disabled by default.** Creates one record, subject to explicit server configuration, authentication, a table allowlist, and field validation. |

Supported table links follow the pattern `https://<tenant>.feishu.cn/base/<base_token>?table=<table_id>`, with an optional `view` parameter. Wiki links, shortened links, the international Lark domain, and general documents are not supported. The `view` argument is forwarded to the upstream API; a view **is not an authorization boundary**.

No tools for editing existing records, deleting records, creating tables, or editing ordinary Feishu documents are implemented.

## Install and run

Python 3.11 or later is required.

```bash
git clone https://github.com/a2681220474-glitch/feishu-bitable-mcp.git
cd feishu-bitable-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
cp .env.example .env
```

Set the credentials of a **Feishu China custom app** in your local `.env`:

```dotenv
FEISHU_APP_ID=
FEISHU_APP_SECRET=
```

Create the app and grant it the relevant table API and resource permissions in the [Feishu Developer Console](https://open.feishu.cn/app). Do not paste credentials into issues, public chats, or repository files.

Start the Streamable HTTP MCP server:

```bash
feishu-bitable-mcp
```

Local MCP URL: `http://127.0.0.1:8000/mcp`. For clients that support local stdio transport:

```bash
feishu-bitable-mcp --transport stdio
```

See [the complete Chinese README](README.md) for MCP initialization requests, Windows notes, and configuration details.

## Remote access, authentication, and writes

The Feishu app secret grants upstream API access; it **does not authenticate callers of your MCP server**.

- For non-loopback HTTP binding, configure a random `MCP_AUTH_TOKEN` (at least 32 characters); the client must support `Authorization: Bearer …`.
- Exposing a local port through an HTTPS tunnel still makes it remotely reachable. Never expose an unauthenticated business-data service.
- This project is not an OAuth authorization server. Some remote MCP clients, including certain ChatGPT configurations, may require an external OAuth/OIDC gateway. **End-to-end ChatGPT web authentication has not been verified for this release.**
- Use `FEISHU_READ_TABLE_URLS` to restrict readable tables when needed.
- To enable the optional creation tool, set `FEISHU_ENABLE_WRITES=true`, `MCP_AUTH_TOKEN`, and `FEISHU_WRITE_TABLE_URLS`. The server validates supported field types and rejects unsupported write types.
- `confirm=true` represents the calling client's assertion of user approval; it is not proof of human authorization. Keep writes disabled unless your client enforces appropriate approval.

This release intentionally does **not** modify existing rows or table schemas, retry uncertain writes, or provide an administrative user interface.

## Testing and limitations

```bash
python -m pip install '.[dev]'
ruff check src tests examples
pytest -q
python -m build
```

The initial public release contains **203 mock-based tests** and a CI matrix for Python 3.11–3.13. It includes fictional-data examples under `examples/`. Mock tests establish expected code behavior, **not successful integration with a production Feishu tenant or Lark international tenant**.

The project uses Feishu tenant app credentials, not per-user OAuth. Its data access is constrained by the **app's** granted permissions, not automatically by the individual human requesting the data. Pagination is explicit; callers must follow `has_more` and `page_token`. Errors and logs are designed to avoid leaking credentials.

## Relationship to official tools

The official [Feishu/Lark OpenAPI MCP](https://github.com/larksuite/lark-openapi-mcp) supports a broader API surface and separate China/international domain settings. For comprehensive Feishu/Lark integrations or user OAuth, evaluate it first. This repository deliberately provides a small, inspectable, URL-oriented subset with conservative defaults.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contributions, [SECURITY.md](SECURITY.md) for vulnerability reports, and [LICENSE](LICENSE) for the MIT license.
