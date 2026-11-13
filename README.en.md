# Feishu Bitable MCP

**English** | [简体中文](README.md) | [日本語](README.ja.md)

A self-hosted Feishu MCP server for Bitable, cloud documents, online spreadsheets and uploaded Excel files. The original goal was to give ChatGPT a Feishu table URL and analyze its data without repeatedly exporting Excel.

**Development candidate 0.2.0rc1:** Feishu user login and the new document/Excel tools are implemented and tested with synthetic APIs. Real Feishu + ChatGPT browser acceptance is pending. Published v0.1.1 does not contain these additions. This community project is not an official Feishu or OpenAI product; international Lark is unsupported.

## Independent deployment

Each deployer uses their own Feishu app, credentials, account and HTTPS service. Approval from the maintainer is not required. No OpenAI API key is needed. Feishu app setup and a reachable MCP service are still necessary; publishing source code does not provide hosting.

In user mode, ChatGPT starts a Feishu OAuth login through the SDK proxy. Each request uses its authenticated user's credential. Refresh is supported; when revoked or no longer refreshable, reconnect and sign in. Effective access remains subject to user permissions, granted app scopes and enterprise policy. User mode is read-only.

## Tools

| Tool | Reads |
| --- | --- |
| get_bitable_info | Base and exact table metadata |
| list_fields | All field pages and raw properties |
| list_records | One record page plus continuation cursor |
| inspect_table | Schema, metadata and first-page samples |
| resolve_resource | Resource type/token, including Wiki resolution |
| read_document | One page of raw docx blocks with styles/tree references |
| get_spreadsheet_info | Spreadsheet and all worksheet properties |
| read_spreadsheet | Explicit rectangle, up to 5000 cells; value/formula rendering |
| read_excel_file | Uploaded Drive .xlsx worksheet values/types/formats and row cursor |

App identity remains available for existing deployments. Optional create_record retains authentication, allowlisting, field validation and confirmation requirements; it cannot be enabled in user mode. No update/delete/schema mutation tools are provided.

## Install and connect

From the source version containing this README, using Python 3.11–3.13:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
feishu-bitable-mcp --setup
feishu-bitable-mcp --doctor
feishu-bitable-mcp
```

The wizard privately saves your app ID/secret and public HTTPS /mcp URL without overwriting an existing config. Add your service's /auth/callback URL in Feishu, enable approved read scopes, publish/approve the app as required, and forward the entire HTTP service. Add the HTTPS /mcp URL in ChatGPT, choose OAuth, and sign in to Feishu. See [complete setup](docs/setup.md) and [authorization boundaries](docs/user-access.md) (Chinese). Use --env-file to start from another directory; environment variables take priority. Default HTTP endpoint: 127.0.0.1:8000/mcp.

## Limits and validation

Follow pagination/windows explicitly. Document blocks preserve embedded object references but do not render/download them automatically. Online Sheets reads do not promise complete styling. Excel accepts ordinary uploaded .xlsx files (20 MiB download, 100 MiB expanded ZIP, 5000 cells/window), without formula/macro execution. Cached formula values can be missing or stale. Legacy .xls, macro/encrypted workbooks and local computer paths are unsupported.

Tests use synthetic records, signed-token/JWKS fixtures and a complete mocked Feishu OAuth flow covering consent, PKCE, refresh, revocation and user isolation. They do not prove tenant permissions or live ChatGPT compatibility. Historical live read/write tests belong to an older private prototype, not this release.

Never publish .env, OAuth state, tokens or business data. See [security](SECURITY.md), [contributing](CONTRIBUTING.md), [changes](CHANGELOG.md), and [MIT license](LICENSE). The official [Feishu CLI](https://github.com/larksuite/cli) and [OpenAPI MCP](https://github.com/larksuite/lark-openapi-mcp) have broader coverage; this project keeps a small URL-oriented tool surface and explicit read budgets.
